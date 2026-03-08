import React, { useState } from 'react'
import { ArrowUp } from 'lucide-react'
import { motion } from 'framer-motion'
import { cn } from '../lib/utils'

interface ChatInputProps {
    onSend: (message: string) => void
    disabled?: boolean
    useRag: boolean
    onToggleRag: (value: boolean) => void
}

export function ChatInput({ onSend, disabled, useRag, onToggleRag }: ChatInputProps) {
    const [input, setInput] = useState('')

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        if (input.trim() && !disabled) {
            onSend(input)
            setInput('')
        }
    }

    return (
        <form onSubmit={handleSubmit} className="relative w-full max-w-2xl mx-auto space-y-3">
            <div className="flex justify-end px-2">
                <label className="flex items-center gap-2 cursor-pointer group">
                    <span className={cn("text-xs font-medium transition-colors", useRag ? "text-blue-600" : "text-gray-400")}>
                        {useRag ? "Legal Mode (RAG)" : "General Knowledge"}
                    </span>
                    <div
                        className={cn(
                            "w-8 h-4.5 rounded-full relative transition-colors duration-300",
                            useRag ? "bg-blue-600" : "bg-gray-300"
                        )}
                        onClick={() => onToggleRag(!useRag)}
                    >
                        <motion.div
                            className="w-3.5 h-3.5 bg-white rounded-full absolute top-0.5 shadow-sm"
                            animate={{ left: useRag ? "calc(100% - 1.125rem)" : "0.125rem" }}
                            transition={{ type: "spring", stiffness: 500, damping: 30 }}
                        />
                    </div>
                </label>
            </div>

            <div className="relative flex items-center bg-[#f4f4f4] rounded-[26px] border border-transparent focus-within:border-gray-300 focus-within:bg-white transition-all duration-200">
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    disabled={disabled}
                    placeholder={useRag ? "Ask a legal question..." : "Ask general questions..."}
                    className={cn(
                        "w-full px-5 py-3.5 pr-14 bg-transparent rounded-[26px] outline-none",
                        "text-gray-900 placeholder:text-gray-500 font-medium",
                        "disabled:opacity-50 disabled:cursor-not-allowed"
                    )}
                />
                <div className="absolute right-2 flex items-center">
                    <motion.button
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        type="submit"
                        disabled={!input.trim() || disabled}
                        className={cn(
                            "p-2 rounded-full bg-black text-white transition-all duration-200",
                            "hover:bg-gray-800 disabled:opacity-20 disabled:cursor-not-allowed flex items-center justify-center",
                            input.trim() ? "opacity-100" : "opacity-20 cursor-default"
                        )}
                    >
                        <ArrowUp size={18} strokeWidth={2.5} />
                    </motion.button>
                </div>
            </div>
        </form>
    )
}

