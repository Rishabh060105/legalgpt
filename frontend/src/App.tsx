import { useState, useRef, useEffect } from 'react'
import { ChatInput } from './components/ChatInput'
import { MessageBubble } from './components/MessageBubble'
import { motion, AnimatePresence } from 'framer-motion'
import { BlurText } from './components/BlurText'
import { consumeSseBuffer } from './lib/sse'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: { id: string, title: string, url: string, excerpt: string, full_text?: string }[]
}

function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: 'Hello! I am LegalGPT. I can help you research legal questions, find case law, and understand statutes. How can I assist you today?'
    }
  ])
  const [loading, setLoading] = useState(false)
  const [useRag, setUseRag] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSend = async (question: string) => {
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: question
    }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)

    try {
      const response = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, use_rag: useRag })
      })

      if (!response.ok) throw new Error('Network response was not ok')
      if (!response.body) throw new Error('No response body')

      // Create placeholder for AI message
      const aiMsgId = (Date.now() + 1).toString()
      const aiMsg: Message = {
        id: aiMsgId,
        role: 'assistant',
        content: '',
        sources: []
      }
      setMessages(prev => [...prev, aiMsg])

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let done = false
      let accumulatedContent = ''
      let sseBuffer = ''

      while (!done) {
        const { value, done: doneReading } = await reader.read()
        done = doneReading

        sseBuffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })
        const { events, remainder } = consumeSseBuffer(sseBuffer, done)
        sseBuffer = remainder

        for (const event of events) {
          if (event.done) {
            done = true
            break
          }

          if (!event.payload || typeof event.payload !== 'object') {
            continue
          }

          const payload = event.payload as { content?: string, sources?: Message['sources'] }
          if (payload.content) {
            accumulatedContent += payload.content
            setMessages(prev =>
              prev.map(msg =>
                msg.id === aiMsgId
                  ? { ...msg, content: accumulatedContent }
                  : msg
              )
            )
          } else if (payload.sources) {
            setMessages(prev =>
              prev.map(msg =>
                msg.id === aiMsgId
                  ? { ...msg, sources: payload.sources }
                  : msg
              )
            )
          }
        }
      }

    } catch (error) {
      console.error(error)
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: "I'm sorry, I encountered an error while processing your request. Please try again."
      }
      setMessages(prev => [...prev, errorMsg])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-screen bg-[#fbfbfd]">
      {/* Header */}
      <header className="flex-none border-b border-gray-200/50 bg-white/80 backdrop-blur-xl sticky top-0 z-10 transition-all">
        <div className="w-full px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3 group cursor-pointer">
            <div className="w-9 h-9 bg-black rounded-lg flex items-center justify-center text-white font-bold shadow-sm group-hover:scale-105 transition-transform duration-300">
              <span className="text-sm">L</span>
            </div>
            <h1 className="text-lg font-semibold tracking-tight text-[#1d1d1f]">
              <BlurText
                text="LegalGPT"
                className="text-lg font-semibold tracking-tight text-[#1d1d1f]"
                delay={50}
              />
            </h1>
          </div>
          <button className="text-[13px] font-medium text-gray-600 hover:text-black transition-colors bg-gray-100 hover:bg-gray-200 px-4 py-2 rounded-lg">
            New Chat
          </button>
        </div>
      </header>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto scroll-smooth">
        <div className="max-w-3xl mx-auto w-full space-y-6 p-4 sm:p-8 pb-32">
          <AnimatePresence initial={false}>
            {messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                role={msg.role}
                content={msg.content}
                sources={msg.sources}
              />
            ))}
            {loading && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex w-full max-w-3xl mx-auto gap-4 py-6"
              >
                <div className="flex-shrink-0 w-9 h-9 rounded-full bg-black text-white flex items-center justify-center shadow-sm">
                  <div className="font-bold text-sm">L</div>
                </div>
                <div className="flex items-center gap-1.5 bg-white border border-gray-100/50 px-5 py-4 rounded-[20px] rounded-tl-[4px] shadow-[0_2px_8px_rgb(0,0,0,0.04)]">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <div className="flex-none fixed bottom-0 w-full p-4 sm:p-6 bg-gradient-to-t from-[#fbfbfd] via-[#fbfbfd]/95 to-transparent z-20">
        <ChatInput
          onSend={handleSend}
          disabled={loading}
          useRag={useRag}
          onToggleRag={setUseRag}
        />
        <p className="text-center text-[11px] text-gray-400 mt-4 font-medium tracking-wide">
          LegalGPT can make mistakes. Verify important information.
        </p>
      </div>
    </div>
  )
}

export default App
