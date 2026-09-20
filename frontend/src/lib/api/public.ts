import apiClient from './client'

export interface PublicNotebook {
  id: string
  name: string
  description: string
}

export interface PublicSource {
  id: string
  title: string | null
  topics: string[] | null
  full_text: string | null
}

export interface PublicNote {
  id: string
  title: string | null
  content: string | null
}

export const publicApi = {
  getNotebook: async (notebookId: string) => {
    const response = await apiClient.get<PublicNotebook>(
      `/public/notebooks/${notebookId}`
    )
    return response.data
  },
  getSources: async (notebookId: string) => {
    const response = await apiClient.get<PublicSource[]>(
      `/public/notebooks/${notebookId}/sources`
    )
    return response.data
  },
  getNotes: async (notebookId: string) => {
    const response = await apiClient.get<PublicNote[]>(
      `/public/notebooks/${notebookId}/notes`
    )
    return response.data
  },
}