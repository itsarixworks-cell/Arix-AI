export type MemoryCategory = 'identity' | 'preferences' | 'projects' | 'relationships' | 'wishes' | 'notes'
export interface MemoryConnection { to: string; relation: string; weight: number }
export interface MemoryNode { id:string; title:string; summary:string; category:MemoryCategory; color:string; size:number; connections:MemoryConnection[]; importance:number; created_at:string; last_accessed:string; access_count:number; source:'manager'|'live_direct'|'migration'|'anchor'; archived:boolean }
export interface MemoryGraphSnapshot { nodes:Record<string,MemoryNode>; edges:Record<string,Record<string,{relation:string;weight:number}>>; title_index:Record<string,{title:string;category:MemoryCategory;color:string;importance:number;last_accessed:string}>; anchors:Record<string,boolean> }
export const MEMORY_CATEGORY_COLORS: Record<MemoryCategory,string> = { identity:'#48D9FF',preferences:'#A77BFF',projects:'#FFB55F',relationships:'#FF6B9E',wishes:'#61E7A8',notes:'#8290A6' }
