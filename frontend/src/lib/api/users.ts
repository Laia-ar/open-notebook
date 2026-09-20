import apiClient from './client'
import { UserSearchResult } from '@/lib/types/api'

export const usersApi = {
  search: async (query: string) => {
    const response = await apiClient.get<UserSearchResult[]>('/users/search', {
      params: { q: query },
    })
    return response.data
  },
}