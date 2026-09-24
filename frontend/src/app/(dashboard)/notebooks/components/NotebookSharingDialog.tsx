'use client'

import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { X, Globe, Lock } from 'lucide-react'
import { NotebookResponse } from '@/lib/types/api'
import {
  useUpdateNotebook,
  useNotebookShares,
  useShareNotebook,
  useUnshareNotebook,
  useUpdateShareRole,
  useUserSearch,
} from '@/lib/hooks/use-notebooks'

interface NotebookSharingDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  notebook: NotebookResponse
}

export function NotebookSharingDialog({
  open,
  onOpenChange,
  notebook,
}: NotebookSharingDialogProps) {
  const [emailInput, setEmailInput] = useState('')

  const updateNotebook = useUpdateNotebook()
  const { data: shares = [] } = useNotebookShares(notebook.id, open)
  const shareNotebook = useShareNotebook()
  const unshareNotebook = useUnshareNotebook()
  const updateShareRole = useUpdateShareRole()
  const { data: suggestions = [] } = useUserSearch(emailInput)

  const handleVisibilityChange = (value: string) => {
    updateNotebook.mutate({
      id: notebook.id,
      data: { is_public: value === 'public' },
    })
  }

  const handlePublicRoleChange = (role: string) => {
    updateNotebook.mutate({
      id: notebook.id,
      data: { public_role: role as 'viewer' | 'editor' },
    })
  }

  const addEmail = (email: string) => {
    const trimmed = email.trim().toLowerCase()
    if (!trimmed) return
    shareNotebook.mutate({ notebookId: notebook.id, email: trimmed, role: 'viewer' })
    setEmailInput('')
  }

  const alreadyShared = new Set(shares.map((s) => s.email))
  const visibleSuggestions = suggestions.filter((u) => !alreadyShared.has(u.email))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Compartir &quot;{notebook.name}&quot;</DialogTitle>
          <DialogDescription>
            Invitá personas específicas, o dejalo público para cualquiera con el link.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="relative">
            <Input
              value={emailInput}
              onChange={(e) => setEmailInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  addEmail(emailInput)
                }
              }}
              placeholder="Agregar personas por email"
              autoComplete="off"
            />
            {visibleSuggestions.length > 0 && (
              <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-md">
                {visibleSuggestions.map((user) => (
                  <button
                    key={user.email}
                    type="button"
                    className="w-full text-left px-3 py-2 text-sm hover:bg-accent"
                    onClick={() => addEmail(user.email)}
                  >
                    <div className="font-medium">{user.name}</div>
                    <div className="text-muted-foreground text-xs">{user.email}</div>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-2">
            <Label className="text-muted-foreground text-xs">
              Personas que tienen acceso
            </Label>

            <div className="flex items-center justify-between py-1">
              <span className="text-sm">Vos (propietario)</span>
              <span className="text-xs text-muted-foreground">Propietario</span>
            </div>

            {shares.map((share) => (
              <div key={share.email} className="flex items-center justify-between gap-2 py-1">
                <span className="text-sm truncate">{share.email}</span>
                <div className="flex items-center gap-1">
                  <Select
                    value={share.role}
                    onValueChange={(role) =>
                      updateShareRole.mutate({
                        notebookId: notebook.id,
                        email: share.email,
                        role: role as 'viewer' | 'editor',
                      })
                    }
                  >
                    <SelectTrigger className="h-8 w-[110px] text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="viewer">Lector</SelectItem>
                      <SelectItem value="editor">Editor</SelectItem>
                    </SelectContent>
                  </Select>
                  <button
                    type="button"
                    onClick={() =>
                      unshareNotebook.mutate({ notebookId: notebook.id, email: share.email })
                    }
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="space-y-2 pt-2 border-t">
            <Label className="text-muted-foreground text-xs">Acceso general</Label>
            <button
              type="button"
              onClick={() => handleVisibilityChange('private')}
              className={`w-full flex items-start gap-3 rounded-md border p-3 text-left ${
                !notebook.is_public ? 'border-primary bg-accent' : ''
              }`}
            >
              <Lock className="h-4 w-4 mt-0.5 shrink-0" />
              <div>
                <div className="text-sm font-medium">Privado</div>
                <div className="text-xs text-muted-foreground">
                  Solo vos y las personas invitadas arriba pueden entrar.
                </div>
              </div>
            </button>

            <div
              className={`w-full rounded-md border p-3 ${
                notebook.is_public ? 'border-primary bg-accent' : ''
              }`}
            >
              <button
                type="button"
                onClick={() => handleVisibilityChange('public')}
                className="w-full flex items-start gap-3 text-left"
              >
                <Globe className="h-4 w-4 mt-0.5 shrink-0" />
                <div>
                  <div className="text-sm font-medium">Público</div>
                  <div className="text-xs text-muted-foreground">
                    Cualquiera con el link puede entrar sin loguearse.
                  </div>
                </div>
              </button>

              {notebook.is_public && (
                <div className="mt-2 pl-7">
                  <Select value={notebook.public_role} onValueChange={handlePublicRoleChange}>
                    <SelectTrigger className="h-8 w-[110px] text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="viewer">Lector</SelectItem>
                      <SelectItem value="editor">Editor</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button type="button" onClick={() => onOpenChange(false)}>
            Listo
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}