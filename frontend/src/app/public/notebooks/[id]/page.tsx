'use client'

import { useQuery } from '@tanstack/react-query'
import { useParams } from 'next/navigation'
import { publicApi } from '@/lib/api/public'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'

export default function PublicNotebookPage() {
  const params = useParams()
  const notebookId = decodeURIComponent(params.id as string)

  const { data: notebook, isLoading, isError } = useQuery({
    queryKey: ['public', 'notebook', notebookId],
    queryFn: () => publicApi.getNotebook(notebookId),
  })

  const { data: sources = [] } = useQuery({
    queryKey: ['public', 'notebook', notebookId, 'sources'],
    queryFn: () => publicApi.getSources(notebookId),
    enabled: !!notebook,
  })

  const { data: notes = [] } = useQuery({
    queryKey: ['public', 'notebook', notebookId, 'notes'],
    queryFn: () => publicApi.getNotes(notebookId),
    enabled: !!notebook,
  })

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <LoadingSpinner />
      </div>
    )
  }

  if (isError || !notebook) {
    return (
      <div className="flex h-screen items-center justify-center text-center px-4">
        <div>
          <h1 className="text-xl font-semibold">No se pudo abrir este notebook</h1>
          <p className="text-muted-foreground mt-2">
            O no existe, o su dueño lo puso en modo privado.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-10">
      <div className="mb-8 border-b pb-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
          Notebook público — {notebook.public_role === 'editor' ? 'Editor' : 'Solo lectura'}
        </div>
        <h1 className="text-2xl font-bold">{notebook.name}</h1>
        {notebook.description && (
          <p className="text-muted-foreground mt-1">{notebook.description}</p>
        )}
      </div>

      <section className="mb-10">
        <h2 className="text-lg font-semibold mb-3">Fuentes</h2>
        {sources.length === 0 && (
          <p className="text-sm text-muted-foreground">No hay fuentes todavía.</p>
        )}
        <div className="space-y-4">
          {sources.map((source) => (
            <div key={source.id} className="border rounded-md p-4">
              <div className="font-medium mb-1">{source.title || 'Sin título'}</div>
              {source.full_text && (
                <p className="text-sm text-muted-foreground whitespace-pre-wrap line-clamp-6">
                  {source.full_text}
                </p>
              )}
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">Notas</h2>
        {notes.length === 0 && (
          <p className="text-sm text-muted-foreground">No hay notas todavía.</p>
        )}
        <div className="space-y-4">
          {notes.map((note) => (
            <div key={note.id} className="border rounded-md p-4">
              {note.title && <div className="font-medium mb-1">{note.title}</div>}
              {note.content && (
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                  {note.content}
                </p>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}