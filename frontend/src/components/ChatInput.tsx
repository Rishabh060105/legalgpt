import React, { useEffect, useRef, useState } from 'react'
import { ArrowUp, Mic, Square } from 'lucide-react'
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
    const [isRecording, setIsRecording] = useState(false)
    const [isTranscribing, setIsTranscribing] = useState(false)
    const [micError, setMicError] = useState('')
    const mediaRecorderRef = useRef<MediaRecorder | null>(null)
    const streamRef = useRef<MediaStream | null>(null)
    const audioChunksRef = useRef<Blob[]>([])

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        if (input.trim() && !disabled && !isTranscribing) {
            onSend(input)
            setInput('')
        }
    }

    useEffect(() => {
        return () => {
            mediaRecorderRef.current?.stop()
            streamRef.current?.getTracks().forEach((track) => track.stop())
        }
    }, [])

    const transcribeAudio = async (audioBlob: Blob) => {
        setIsTranscribing(true)
        setMicError('')

        try {
            const extension = audioBlob.type.includes('webm') ? 'webm' : 'wav'
            const formData = new FormData()
            formData.append('audio', audioBlob, `legalgpt-recording.${extension}`)

            const response = await fetch('/api/transcribe', {
                method: 'POST',
                body: formData,
            })

            const payload = await response.json()
            if (!response.ok) {
                throw new Error(payload.detail || 'Transcription failed')
            }

            if (typeof payload.text === 'string' && payload.text.trim()) {
                setInput((current) => (current ? `${current} ${payload.text}` : payload.text))
                return
            }

            throw new Error('No speech could be transcribed')
        } catch (error) {
            console.error(error)
            setMicError(error instanceof Error ? error.message : 'Microphone transcription failed')
        } finally {
            setIsTranscribing(false)
        }
    }

    const stopRecording = async () => {
        const recorder = mediaRecorderRef.current
        if (!recorder || recorder.state === 'inactive') {
            return
        }

        recorder.stop()
        setIsRecording(false)
    }

    const startRecording = async () => {
        if (disabled || isTranscribing) {
            return
        }

        setMicError('')

        if (!navigator.mediaDevices?.getUserMedia) {
            setMicError('Microphone recording is not supported in this browser')
            return
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
            const recorder = new MediaRecorder(stream)

            streamRef.current = stream
            mediaRecorderRef.current = recorder
            audioChunksRef.current = []

            recorder.addEventListener('dataavailable', (event) => {
                if (event.data.size > 0) {
                    audioChunksRef.current.push(event.data)
                }
            })

            recorder.addEventListener('stop', async () => {
                const blobType = recorder.mimeType || 'audio/webm'
                const audioBlob = new Blob(audioChunksRef.current, { type: blobType })
                stream.getTracks().forEach((track) => track.stop())
                streamRef.current = null
                mediaRecorderRef.current = null

                if (audioBlob.size > 0) {
                    await transcribeAudio(audioBlob)
                } else {
                    setMicError('No audio was captured')
                }
            })

            recorder.start()
            setIsRecording(true)
        } catch (error) {
            console.error(error)
            setMicError('Microphone access was denied or unavailable')
        }
    }

    const handleMicClick = async () => {
        if (isRecording) {
            await stopRecording()
            return
        }

        await startRecording()
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
                    disabled={disabled || isTranscribing}
                    placeholder={
                        isTranscribing
                            ? 'Transcribing your speech...'
                            : useRag
                                ? 'Ask a legal question...'
                                : 'Ask general questions...'
                    }
                    className={cn(
                        "w-full px-5 py-3.5 pr-14 bg-transparent rounded-[26px] outline-none",
                        "text-gray-900 placeholder:text-gray-500 font-medium",
                        "disabled:opacity-50 disabled:cursor-not-allowed"
                    )}
                />
                <div className="absolute right-2 flex items-center gap-2">
                    <motion.button
                        whileHover={{ scale: disabled || isTranscribing ? 1 : 1.05 }}
                        whileTap={{ scale: disabled || isTranscribing ? 1 : 0.95 }}
                        type="button"
                        onClick={handleMicClick}
                        disabled={disabled || isTranscribing}
                        className={cn(
                            "p-2 rounded-full transition-all duration-200 flex items-center justify-center",
                            isRecording ? "bg-red-500 text-white hover:bg-red-600" : "bg-white text-gray-700 hover:bg-gray-100",
                            "border border-gray-200 disabled:opacity-40 disabled:cursor-not-allowed"
                        )}
                        aria-label={isRecording ? 'Stop recording' : 'Start recording'}
                    >
                        {isRecording ? <Square size={16} strokeWidth={2.5} /> : <Mic size={16} strokeWidth={2.5} />}
                    </motion.button>
                    <motion.button
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        type="submit"
                        disabled={!input.trim() || disabled || isTranscribing}
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
            {(isRecording || isTranscribing || micError) && (
                <div className="px-2 text-xs font-medium">
                    {isRecording && <p className="text-red-500">Recording... tap the square to stop.</p>}
                    {isTranscribing && <p className="text-blue-600">Converting speech to text...</p>}
                    {micError && <p className="text-red-500">{micError}</p>}
                </div>
            )}
        </form>
    )
}
