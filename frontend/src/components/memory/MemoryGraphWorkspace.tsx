import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph3D, {
  type ForceGraph3DInstance,
  type LinkObject,
  type NodeObject,
} from '3d-force-graph'
import { BrainCircuit, RotateCcw } from 'lucide-react'
import SpriteText from 'three-spritetext'
import { useMemoryGraph } from '../../hooks/memory/useMemoryGraph'
import {
  MEMORY_CATEGORY_COLORS,
  type MemoryCategory,
  type MemoryNode,
} from '../../types/memory'
import { MemoryDetailPanel } from './MemoryDetailPanel'
import { MemoryFilters } from './MemoryFilters'

type GraphNode = NodeObject & MemoryNode
type GraphLink = LinkObject<GraphNode> & { relation: string; weight: number }

const ALL_CATEGORIES = new Set(
  Object.keys(MEMORY_CATEGORY_COLORS) as MemoryCategory[],
)

export function MemoryGraphWorkspace() {
  const { graph, connected } = useMemoryGraph(true)
  const host = useRef<HTMLDivElement>(null)
  const instance = useRef<ForceGraph3DInstance<GraphNode, GraphLink> | null>(null)
  const [selected, setSelected] = useState<MemoryNode | null>(null)
  const [search, setSearch] = useState('')
  const [categories, setCategories] = useState(new Set(ALL_CATEGORIES))
  const [minimum, setMinimum] = useState(0)

  const data = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase()
    const visible = Object.values(graph.nodes).filter(
      (node) =>
        graph.anchors[node.id] ||
        (categories.has(node.category) &&
          node.importance >= minimum &&
          node.title.toLowerCase().includes(normalizedSearch)),
    )
    const visibleIds = new Set(visible.map((node) => node.id))
    const nodes = visible.map((node) => ({
      ...node,
      ...(node.id === 'ai_root'
        ? { fx: -24, fy: 0, fz: 0 }
        : node.id === 'user_root'
          ? { fx: 24, fy: 0, fz: 0 }
          : {}),
    })) as GraphNode[]
    const links: GraphLink[] = []

    for (const [source, targets] of Object.entries(graph.edges)) {
      for (const [target, edge] of Object.entries(targets)) {
        if (source < target && visibleIds.has(source) && visibleIds.has(target)) {
          links.push({
            source,
            target,
            relation: edge.relation,
            weight: edge.weight,
          })
        }
      }
    }

    return { nodes, links }
  }, [categories, graph, minimum, search])

  useEffect(() => {
    const container = host.current
    if (!container) return

    const forceGraph = new ForceGraph3D(container, {
      controlType: 'orbit',
    }) as unknown as ForceGraph3DInstance<GraphNode, GraphLink>

    forceGraph
      .backgroundColor('#07080b')
      .showNavInfo(false)
      .nodeId('id')
      .nodeVal((node) =>
        graph.anchors[node.id] ? 10 : Math.max(1, node.size + node.importance * 2),
      )
      .nodeColor((node) => node.color)
      .nodeOpacity(0.92)
      .nodeResolution(16)
      .linkColor(() => '#62718c')
      .linkOpacity(0.24)
      .linkWidth((link) => 0.25 + link.weight * 1.25)
      .nodeLabel(
        (node) =>
          `<b>${node.title}</b><br/><span>${node.category}</span><br/><small>${node.summary.slice(0, 100)}</small>`,
      )
      .nodeThreeObject((node) => {
        const label = new SpriteText(node.title)
        label.color = node.color
        label.textHeight = graph.anchors[node.id] ? 4 : 2.4
        label.position.y = graph.anchors[node.id] ? 10 : 5 + node.size
        label.backgroundColor = 'rgba(7,8,11,.68)'
        label.padding = 0.8
        label.borderRadius = 2
        return label
      })
      .nodeThreeObjectExtend(true)
      .onNodeClick((node) => {
        setSelected(node)
        const x = node.x ?? 1
        const y = node.y ?? 1
        const z = node.z ?? 1
        const ratio = 1 + 48 / Math.hypot(x, y, z)
        forceGraph.cameraPosition(
          { x: x * ratio, y: y * ratio, z: z * ratio },
          { x, y, z },
          700,
        )
      })
      .onBackgroundClick(() => setSelected(null))

    instance.current = forceGraph
    const resize = new ResizeObserver(([entry]) => {
      forceGraph.width(entry.contentRect.width).height(entry.contentRect.height)
    })
    resize.observe(container)

    return () => {
      resize.disconnect()
      forceGraph._destructor()
      instance.current = null
    }
  }, [graph.anchors])

  useEffect(() => {
    instance.current?.graphData(data)
  }, [data])

  const toggleCategory = (category: MemoryCategory) => {
    setCategories((current) => {
      const next = new Set(current)
      if (next.has(category)) next.delete(category)
      else next.add(category)
      return next
    })
  }

  return (
    <main className="memory-workspace" id="memory-workspace">
      <header className="workspace-header">
        <div>
          <span className="eyebrow"><BrainCircuit size={12} /> GRAPH MEMORY</span>
          <h1>Memory constellation</h1>
        </div>
        <div className="memory-live">
          <i className={connected ? 'online' : ''} />
          {connected ? 'Live sync' : 'Local bridge offline'}
          <button onClick={() => instance.current?.zoomToFit(700, 80)}>
            <RotateCcw size={13} /> Fit graph
          </button>
        </div>
      </header>
      <MemoryFilters
        search={search}
        onSearch={setSearch}
        categories={categories}
        onToggle={toggleCategory}
        minimum={minimum}
        onMinimum={setMinimum}
      />
      <section className="memory-canvas" aria-label="Memory graph visualization">
        <div ref={host} className="memory-graph-host" />
        {data.nodes.length === 0 && (
          <div className="memory-graph-empty">
            <BrainCircuit size={28} />
            <p>No memories match these filters.</p>
          </div>
        )}
        <div className="memory-stats">
          <span>{data.nodes.length} dots</span>
          <span>{data.links.length} connections</span>
        </div>
        {selected && (
          <MemoryDetailPanel
            node={selected}
            nodes={graph.nodes}
            onSelect={setSelected}
            onClose={() => setSelected(null)}
          />
        )}
      </section>
    </main>
  )
}
