import { createContext, useContext } from 'react'
import useChat from '../hooks/useChat'

const ChatContext = createContext(null)

export function ChatProvider({ children }) {
  const chat = useChat()
  return (
    <ChatContext.Provider value={chat}>
      {children}
    </ChatContext.Provider>
  )
}

export function useChatContext() {
  const ctx = useContext(ChatContext)
  if (!ctx) throw new Error('useChatContext debe usarse dentro de ChatProvider')
  return ctx
}
