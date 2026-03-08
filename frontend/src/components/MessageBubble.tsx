import { motion } from 'framer-motion'
import { User } from 'lucide-react'
import { cn } from '../lib/utils'
import { useState } from 'react'
import { SourceModal } from './SourceModal'

interface Source {
    id: string
    title: string
    url: string
    excerpt: string
    full_text?: string
}

interface MessageProps {
    role: 'user' | 'assistant'
    content: string
    sources?: Source[]
}

export function MessageBubble({ role, content, sources }: MessageProps) {
    const isUser = role === 'user'
    const [selectedSource, setSelectedSource] = useState<{ title: string, subtitle: string, content: string } | null>(null)

    return (
        <>
            <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={cn(
                    "flex w-full max-w-3xl mx-auto gap-4 py-6 px-4 md:px-0",
                    isUser ? "flex-row-reverse" : "flex-row"
                )}
            >
                <div className={cn(
                    "flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center shadow-sm",
                    isUser ? "bg-gray-200 text-gray-500" : "bg-black text-white"
                )}>
                    {isUser ? <User size={18} /> : <div className="font-bold text-sm">L</div>}
                </div>

                <div className={cn(
                    "flex-1 space-y-2 max-w-[85%]",
                    isUser ? "items-end flex flex-col" : "items-start flex flex-col"
                )}>
                    <div className={cn(
                        "inline-block px-5 py-3.5 shadow-sm text-[15px] leading-relaxed",
                        isUser
                            ? "bg-[#007AFF] text-white rounded-[20px] rounded-tr-[4px]" // Apple Blue
                            : "bg-white border border-gray-100/50 text-[#1d1d1f] rounded-[20px] rounded-tl-[4px] shadow-[0_2px_8px_rgb(0,0,0,0.04)]"
                    )}>
                        <p className="whitespace-pre-wrap">{content}</p>
                    </div>

                    {!isUser && sources && sources.length > 0 && (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: 0.3 }}
                            className="flex flex-wrap gap-2 mt-2"
                        >
                            {sources.map((source, index) => (
                                <button
                                    key={source.id}
                                    onClick={() => setSelectedSource({
                                        title: source.title,
                                        subtitle: source.url,
                                        content: source.full_text || source.excerpt
                                    })}
                                    className="group flex items-center gap-2 bg-white border border-gray-200/60 rounded-xl px-3 py-2 transition-all hover:border-blue-300 hover:shadow-sm cursor-pointer text-left"
                                >
                                    <div className="w-5 h-5 rounded-md bg-blue-50 text-blue-600 flex items-center justify-center font-bold text-[10px] group-hover:scale-110 transition-transform">
                                        {index + 1}
                                    </div>
                                    <div className="flex flex-col">
                                        <span className="text-[11px] font-semibold text-gray-900 leading-tight truncate max-w-[140px] group-hover:text-blue-600 transition-colors">
                                            {source.title}
                                        </span>
                                        <span className="text-[10px] text-gray-500 truncate max-w-[140px]">
                                            {source.url}
                                        </span>
                                    </div>
                                </button>
                            ))}
                        </motion.div>
                    )}
                </div>
            </motion.div>

            <SourceModal
                isOpen={!!selectedSource}
                onClose={() => setSelectedSource(null)}
                source={selectedSource}
            />
        </>
    )
}
