// 브라우저 전체 흐름 1 시나리오 (설계서 12장 web e2e, playwright-core + 설치된 Chrome).
//   node e2e/browser_flow.mjs <PDF 경로> [스크린샷 폴더]
// 전제: API 가 127.0.0.1:8000, vite dev 가 127.0.0.1:5173 (또는 E2E_BASE) 에서 동작한다.
// 흐름: 로그인 → 업로드 → ready → 질문 → 근거 카드 클릭 → 해당 페이지 표시, 그리고 무근거 보류 화면.
import { chromium } from 'playwright-core'
import { mkdirSync } from 'node:fs'
import { basename, resolve } from 'node:path'

const pdf = resolve(process.argv[2] ?? '')
const outDir = resolve(process.argv[3] ?? 'e2e-shots')
const base = process.env.E2E_BASE ?? 'http://127.0.0.1:5173'
const user = process.env.E2E_USER ?? 'a_admin'
const pass = process.env.E2E_PASS ?? 'admin-a-demo-2026'
mkdirSync(outDir, { recursive: true })

const log = (step, extra = {}) => console.log(JSON.stringify({ step, ...extra }))
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
const shot = (name) => page.screenshot({ path: `${outDir}/${name}.png`, fullPage: true })

try {
  await page.goto(`${base}/login`)
  await page.waitForLoadState('networkidle')
  await page.getByLabel('아이디').pressSequentially(user)
  await page.getByLabel('비밀번호').fill(pass)
  await shot('01_login')
  await page.getByRole('button', { name: '로그인' }).click()
  await page.getByRole('link', { name: '자료' }).waitFor()
  log('login_ok')

  await page.getByRole('link', { name: '자료' }).click()
  await page.getByRole('radio', { name: /인공지능 기초/ }).check()
  await page.locator('input[type=file]').setInputFiles(pdf)
  await page.getByRole('button', { name: '업로드' }).click()
  const t0 = Date.now()
  await page.getByText('작업 완료').first().waitFor({ timeout: 300_000 })
  const row = page.getByRole('row', { name: new RegExp(basename(pdf)) })
  await row.getByText('사용 가능').waitFor({ timeout: 30_000 })
  log('upload_ready', { seconds: Math.round((Date.now() - t0) / 1000) })
  await shot('02_documents_ready')

  await page.getByRole('link', { name: '질문' }).click()
  await page.getByLabel('질문').fill('교착 상태의 네 가지 필요 조건은?')
  await page.getByRole('button', { name: '질문하기' }).click()
  await page.getByText('근거를 찾고 답변을 만드는 중').waitFor({ timeout: 10_000 }).catch(() => {})
  const card = page.getByRole('button', { name: /쪽 열기$/ }).first()
  await card.waitFor({ timeout: 120_000 })
  const label = await card.getAttribute('aria-label')
  await shot('03_answer')
  log('answer_ok', { first_card: label })

  await card.click()
  const dialog = page.getByRole('dialog')
  await dialog.locator('canvas').first().waitFor({ timeout: 60_000 })
  const pager = await dialog.getByText(/\d+ \/ \d+쪽/).textContent()
  await shot('04_pdf_page')
  log('viewer_ok', { pager })
  await dialog.getByRole('button', { name: '닫기' }).click()

  await page.getByLabel('질문').fill('[[no_evidence]] 양자역학의 불확정성 원리는?')
  await page.getByRole('button', { name: '질문하기' }).click()
  await page.getByRole('heading', { name: '자료에서 확인하지 못했습니다' }).waitFor({ timeout: 120_000 })
  await shot('05_abstain')
  log('abstain_ok')
} catch (e) {
  await shot('99_failure').catch(() => {})
  log('failed', { error: String(e).slice(0, 500) })
  process.exitCode = 1
} finally {
  await browser.close()
}
