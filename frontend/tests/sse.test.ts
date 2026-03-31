import assert from 'node:assert/strict'
import test from 'node:test'

import { consumeSseBuffer } from '../src/lib/sse.ts'

test('consumeSseBuffer preserves partial frames until they are complete', () => {
  const firstPass = consumeSseBuffer('data: {"content":"Hel')
  assert.equal(firstPass.events.length, 0)
  assert.equal(firstPass.remainder, 'data: {"content":"Hel')

  const secondPass = consumeSseBuffer(firstPass.remainder + 'lo"}\n\n')
  assert.equal(secondPass.events.length, 1)
  assert.deepEqual(secondPass.events[0], {
    done: false,
    payload: { content: 'Hello' },
  })
  assert.equal(secondPass.remainder, '')
})

test('consumeSseBuffer parses sources and done frames independently', () => {
  const payload = 'data: {"sources":[{"id":"1","title":"Section 132","url":"Indian_Corporate_Act_2013.pdf","excerpt":"..."}]}\n\ndata: [DONE]\n\n'
  const result = consumeSseBuffer(payload)

  assert.equal(result.events.length, 2)
  assert.equal(result.events[0].done, false)
  assert.deepEqual(result.events[0].payload, {
    sources: [
      {
        id: '1',
        title: 'Section 132',
        url: 'Indian_Corporate_Act_2013.pdf',
        excerpt: '...',
      },
    ],
  })
  assert.deepEqual(result.events[1], { done: true, payload: null })
})
