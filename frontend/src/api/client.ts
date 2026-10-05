/** 统一请求封装：拼后端地址、带操作人身份头、抛网络错误、给页脚留一句可读的说明。 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export function currentOperator(): string {
  return localStorage.getItem('operator-name') ?? '王安全'
}

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  return fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      // HTTP 头只能放 ASCII，中文姓名先 URL 编码，后端再解码
      'X-Operator-Name': encodeURIComponent(currentOperator()),
    },
    ...init,
  }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}
