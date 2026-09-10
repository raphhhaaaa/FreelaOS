import { useEffect, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Loader2, Trash2 } from "lucide-react";
import { DragDropContext, Droppable, Draggable, DropResult } from "@hello-pangea/dnd";
import { toast } from "sonner";
import { useDeleteOportunidade } from "@/queries/oportunidades";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { PageContainer, PageHeader } from "@/components/page-header";
import { currency } from "@/lib/mock-data";
import { supabase } from "@/lib/supabase";
import { api } from "@/core/api";

export const Route = createFileRoute("/projetos")({
  head: () => ({ meta: [{ title: "Projetos · FreelaOS" }] }),
  component: ProjetosPage,
});

type KanbanColumn = "backlog" | "andamento" | "aguardando" | "concluido";

const columns: { id: KanbanColumn; title: string; accent: string }[] = [
  { id: "backlog", title: "Backlog", accent: "bg-muted-foreground" },
  { id: "aguardando", title: "Aguardando cliente", accent: "bg-warning" },
  { id: "andamento", title: "Em andamento", accent: "bg-primary" },
  { id: "concluido", title: "Concluído", accent: "bg-success" },
];

function ProjetosPage() {
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<any[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [lastSelectedId, setLastSelectedId] = useState<string | null>(null);
  const { mutateAsync: deleteOportunidade } = useDeleteOportunidade();

  useEffect(() => {
    async function fetchProjects() {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session?.user?.id) {
        setLoading(false);
        return;
      }
      
      const { data, error } = await supabase
        .from("oportunidades")
        .select(`id, titulo, cliente, orcamento, valor_proposta, status, prazo_proposta, stack`)
        .eq("perfil_id", session.user.id);
        
      if (data) {
        // Mapear os status reais das oportunidades para as colunas do Kanban
        const mappedProjects = data.map((op: any) => {
          let column: KanbanColumn | null = null;
          
          const status = op.status || "";
          
          // "Proposta enviada" e "Em negociação" -> Aguardando cliente
          if (["Proposta enviada", "Proposta Enviada", "Em negociação"].includes(status)) {
            column = "aguardando";
          }
          // "Proposta aceita", "Projeto fechado", "Em andamento" -> Em andamento
          else if (["Proposta aceita", "Projeto fechado", "Em andamento"].includes(status)) {
            column = "andamento";
          }
          // "Finalizado", "Entregue", "Concluído" -> Concluído
          else if (["Finalizado", "Entregue", "Concluído"].includes(status)) {
            column = "concluido";
          }
          // Se o usuário já revisou/salvou a proposta_ia, o status deve ser "Rascunho" ou "Proposta salva"
          // Se for "Aprovada" também fica no backlog.
          else if (["Aprovada", "Rascunho", "Proposta salva"].includes(status) || (op.proposta_ia && op.proposta_ia.length > 0)) {
            column = "backlog";
          }
          
          if (!column) return null; // Ignora as vagas comuns
          
          return {
            id: op.id,
            title: op.titulo,
            client: op.cliente || "Cliente",
            stack: op.stack || [],
            deadline: op.prazo_proposta || "Prazo a definir",
            value: op.valor_proposta || op.orcamento || 0,
            columnId: column
          };
        }).filter(Boolean);
        
        setProjects(mappedProjects);
      }
      setLoading(false);
    }
    
    fetchProjects();
  }, []);

  const onDragStart = (start: any) => {
    if (selectedIds.length > 0 && !selectedIds.includes(start.draggableId)) {
      setSelectedIds([]);
    }
  };

  const handleDragEnd = async (result: DropResult) => {
    const { destination, source, draggableId } = result;

    if (!destination) return;
    if (destination.droppableId === source.droppableId && destination.index === source.index) return;
    if (destination.droppableId === "backlog") return; // Regra: Não pode mover para backlog manualmente

    // Regra: Do backlog só é permitido arrastar para a zona "ignorar"
    if (source.droppableId === "backlog" && destination.droppableId !== "ignorar") return;

    const isDraggingMultiple = selectedIds.length > 1 && selectedIds.includes(draggableId);
    const idsToProcess = isDraggingMultiple ? selectedIds : [draggableId];

    // Caso de arrastar para a zona "Ignorar"
    if (destination.droppableId === "ignorar") {
      const projectsToRestore = projects.filter(p => idsToProcess.includes(p.id));

      // Remove otimisticamente
      setProjects(prev => prev.filter(p => !idsToProcess.includes(p.id)));
      setSelectedIds([]);

      try {
        await Promise.all(idsToProcess.map(id => deleteOportunidade(id)));
        toast.success(idsToProcess.length > 1 ? `${idsToProcess.length} vagas ignoradas.` : "Vaga ignorada.");
      } catch (e: any) {
        toast.error("Erro ao ignorar oportunidade(s).");
        setProjects(prev => [...prev, ...projectsToRestore]);
      }
      return;
    }

    if (isDraggingMultiple) {
      toast.warning("A movimentação em lote é permitida apenas para a lixeira.");
      setSelectedIds([]);
      return;
    }

    // Encontra o projeto
    const project = projects.find(p => p.id === draggableId);
    if (!project) return;

    // Atualiza otimisticamente a UI
    const newProjects = Array.from(projects);
    const index = newProjects.findIndex(p => p.id === draggableId);
    newProjects[index].columnId = destination.droppableId as KanbanColumn;
    setProjects(newProjects);

    // Mapeia a coluna de destino para o Status correspondente no DB
    let novoStatus = "";
    if (destination.droppableId === "aguardando") novoStatus = "Proposta enviada";
    else if (destination.droppableId === "andamento") novoStatus = "Em andamento";
    else if (destination.droppableId === "concluido") novoStatus = "Concluído";

    try {
      await api.patch(`/api/opportunities/${draggableId}`, {
        status: novoStatus
      });
      toast.success(`Projeto movido para ${novoStatus}!`);
    } catch (e: any) {
      toast.error("Erro ao mover o projeto.");
      // Reverte a alteração visual
      newProjects[index].columnId = source.droppableId as KanbanColumn;
      setProjects([...newProjects]);
    }
  };

  return (
    <PageContainer>
      <PageHeader title="Projetos" description="Kanban dos projetos ativos e do pipeline." />

      {loading ? (
        <div className="flex h-64 items-center justify-center text-muted-foreground">
          <Loader2 className="mr-2 h-6 w-6 animate-spin" />
          <span>Carregando projetos...</span>
        </div>
      ) : (
        <DragDropContext onDragStart={onDragStart} onDragEnd={handleDragEnd}>
          <div className="flex w-full items-start gap-4">
            {/* Barra lateral de descarte / Ignorar Vaga */}
            <Droppable droppableId="ignorar">
              {(provided, snapshot) => (
                <div 
                  ref={provided.innerRef}
                  {...provided.droppableProps}
                  className={`flex min-h-[450px] w-20 shrink-0 self-stretch flex-col items-center justify-center rounded-2xl border-2 border-dashed p-2 text-center transition-all duration-200 ${
                    snapshot.isDraggingOver 
                      ? 'border-destructive bg-destructive/15 text-destructive shadow-[0_0_25px_rgba(239,68,68,0.25)] scale-[1.02] opacity-100' 
                      : 'border-border/30 bg-card/10 text-muted-foreground/40 opacity-30 hover:opacity-75 hover:border-destructive/40'
                  }`}
                >
                  <div className={`mb-4 flex h-10 w-10 items-center justify-center rounded-full transition-colors ${
                    snapshot.isDraggingOver ? 'bg-destructive/20 text-destructive' : 'bg-muted/40 text-muted-foreground/60'
                  }`}>
                    <Trash2 className="h-5 w-5" />
                  </div>
                  <span className="text-[11px] font-semibold uppercase tracking-wider [writing-mode:vertical-lr] rotate-180">
                    {snapshot.isDraggingOver ? "Solte para Ignorar" : "Ignorar Vaga"}
                  </span>
                  {provided.placeholder}
                </div>
              )}
            </Droppable>

            {/* Grid das 4 Colunas do Kanban */}
            <div className="grid flex-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
              {columns.map((col) => {
                const items = projects.filter((p) => p.columnId === col.id);
                return (
                  <Droppable key={col.id} droppableId={col.id} isDropDisabled={col.id === "backlog"}>
                    {(provided, snapshot) => (
                      <div 
                        ref={provided.innerRef}
                        {...provided.droppableProps}
                        className={`flex min-h-[400px] flex-col rounded-2xl border border-border/60 bg-card/40 p-3 transition-colors ${snapshot.isDraggingOver ? 'bg-primary/5' : ''}`}
                      >
                        <div className="mb-3 flex items-center justify-between px-1">
                          <div className="flex items-center gap-2">
                            <span className={`h-2 w-2 rounded-full ${col.accent}`} />
                            <p className="text-sm font-medium">{col.title}</p>
                          </div>
                          <span className="rounded-full bg-background/60 px-2 py-0.5 text-xs text-muted-foreground">
                            {items.length}
                          </span>
                        </div>
                        <div className="flex-1 space-y-2">
                          {items.length === 0 && (
                            <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-border/50 text-xs text-muted-foreground/50">
                              Vazio
                            </div>
                          )}
                          {items.map((p, index) => (
                            <Draggable key={p.id} draggableId={p.id} index={index}>
                              {(provided, snapshot) => (
                                <div
                                  ref={provided.innerRef}
                                  {...provided.draggableProps}
                                  {...provided.dragHandleProps}
                                  style={{
                                    ...provided.draggableProps.style,
                                    opacity: snapshot.isDragging ? 0.8 : 1,
                                  }}
                                >
                                  <Link 
                                    to="/oportunidades/$id" 
                                    params={{ id: p.id }} 
                                    className="block relative"
                                    onClick={(e) => {
                                      if (e.shiftKey && lastSelectedId) {
                                        e.preventDefault();
                                        const currentProject = projects.find(proj => proj.id === p.id);
                                        const lastProject = projects.find(proj => proj.id === lastSelectedId);
                                        if (currentProject && lastProject && currentProject.columnId === lastProject.columnId) {
                                          const columnItems = projects.filter(proj => proj.columnId === currentProject.columnId);
                                          const currentIndex = columnItems.findIndex(proj => proj.id === p.id);
                                          const lastIndex = columnItems.findIndex(proj => proj.id === lastSelectedId);
                                          const start = Math.min(currentIndex, lastIndex);
                                          const end = Math.max(currentIndex, lastIndex);
                                          const idsToSelect = columnItems.slice(start, end + 1).map(proj => proj.id);
                                          
                                          setSelectedIds(prev => {
                                            const newSet = new Set([...prev, ...idsToSelect]);
                                            return Array.from(newSet);
                                          });
                                        }
                                      } else if (e.ctrlKey || e.metaKey) {
                                        e.preventDefault();
                                        setSelectedIds(prev =>
                                          prev.includes(p.id) ? prev.filter(x => x !== p.id) : [...prev, p.id]
                                        );
                                        setLastSelectedId(p.id);
                                      }
                                    }}
                                  >
                                    <Card
                                      className={`cursor-pointer border-border/60 bg-background/60 p-3 transition hover:border-primary/40 hover:bg-muted/30 ${snapshot.isDragging ? 'shadow-lg border-primary/50 relative z-50' : ''} ${selectedIds.includes(p.id) ? 'ring-2 ring-primary/80 bg-primary/5' : ''}`}
                                    >
                                      {snapshot.isDragging && selectedIds.includes(p.id) && selectedIds.length > 1 && (
                                        <div className="absolute -top-3 -right-3 flex h-6 items-center justify-center rounded-full bg-primary px-2 text-xs font-bold text-primary-foreground shadow-sm animate-in zoom-in duration-200">
                                          {selectedIds.length} selecionados
                                        </div>
                                      )}
                                      <p className="text-xs text-muted-foreground">{p.client}</p>
                                      <p className="mt-0.5 text-sm font-medium leading-snug">{p.title}</p>
                                      {p.stack && p.stack.length > 0 && (
                                        <div className="mt-3 flex flex-wrap gap-1">
                                          {p.stack.slice(0, 3).map((s: string) => (
                                            <Badge key={s} variant="outline" className="border-border/60 bg-transparent text-[10px]">
                                              {s}
                                            </Badge>
                                          ))}
                                          {p.stack.length > 3 && (
                                            <Badge variant="outline" className="border-border/60 bg-transparent text-[10px]">
                                              +{p.stack.length - 3}
                                            </Badge>
                                          )}
                                        </div>
                                      )}
                                      <div className="mt-3 flex items-center justify-between border-t border-border/50 pt-2 text-xs">
                                        <span className="text-muted-foreground">{p.deadline}</span>
                                        <span className="font-semibold text-primary/90">{currency(p.value)}</span>
                                      </div>
                                    </Card>
                                  </Link>
                                </div>
                              )}
                            </Draggable>
                          ))}
                          {provided.placeholder}
                        </div>
                      </div>
                    )}
                  </Droppable>
                );
              })}
            </div>
          </div>
        </DragDropContext>
      )}
    </PageContainer>
  );
}