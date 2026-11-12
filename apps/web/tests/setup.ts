import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// vitest globals 를 쓰지 않으므로 testing-library 자동 정리가 걸리지 않는다. 직접 등록한다.
afterEach(() => cleanup())
