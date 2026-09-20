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
import { Badge } from '@/components/ui/badge'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { X } from 'lucide-react'
import { NotebookResponse } from '@/lib/types/api'
import {
  useUpdateNotebook,
  useNotebookShares,
  useShareNotebook,
  useUnshareNotebook,
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
  const { data: suggestions = [] } = useUserSearch(emailInput)

  const visibility = notebook.is_public ? 'public' : 'private'

  const handleVisibilityChange = (value: string) => {
    updateNotebook.mutate({
      id: notebook.id,
      data: { is_public: value === 'public' },
    })
  }

  const addEmail = (email: string) => {
    const trimmed = email.trim().toLowerCase()
    if (!trimmed) return
    shareNotebook.mutate({ notebookId: notebook.id, email: trimmed })
    setEmailInput('')
  }

  const alreadyShared = new Set(shares.map((s) => s.email))
  const visibleSuggestions = suggestions.filter((u) => !alreadyShared.has(u.email))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Compartir notebook</DialogTitle>
          <DialogDescription>
            Elegí quién puede ver &quot;{notebook.name}&quot;.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <RadioGroup value={visibility} onValueChange={handleVisibilityChange}>
            <div className="flex items-center space-x-3">
              <RadioGroupItem value="private" id="visibility-private" />
              <Label htmlFor="visibility-private" className="cursor-pointer">
                Privado — solo vos y quien invites
              </Label>
            </div>
            <div className="flex items-center space-x-3">
              <RadioGroupItem value="public" id="visibility-public" />
              <Label htmlFor="visibility-public" className="cursor-pointer">
                Público — cualquier usuario logueado puede verlo
              </Label>
            </div>
          </RadioGroup>

          {visibility === 'private' && (
            <div className="space-y-3 pt-2 border-t">
              <div className="space-y-2 pt-3">
                <Label htmlFor="share-email">Invitar por email</Label>
                <div className="relative">
                  <Input
                    id="share-email"
                    value={emailInput}
                    onChange={(e) => setEmailInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addEmail(emailInput)
                      }
                    }}
                    placeholder="nombre@laia.com.ar"
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
                          <div className="text-muted-foreground text-xs">
                            {user.email}
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {shares.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {shares.map((share) => (
                    <Badge key={share.email} variant="secondary" className="gap-1">
                      {share.email}
                      <button
                        type="button"
                        onClick={() =>
                          unshareNotebook.mutate({
                            notebookId: notebook.id,
                            email: share.email,
                          })
                        }
                        className="ml-1"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}
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