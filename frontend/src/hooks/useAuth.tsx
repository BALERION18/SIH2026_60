import React, { createContext, useContext, useState, useCallback } from 'react'
import { login as apiLogin } from '../api/auth'
import type { UserOut } from '../api/auth'
import { setToken } from '../api/client'

interface AuthCtx {
  token: string | null
  user: UserOut | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthCtx | null>(null)

const TOKEN_KEY = 'vajrax_token'
const USER_KEY  = 'vajrax_user'

function loadPersisted(): { token: string | null; user: UserOut | null } {
  try {
    const token = localStorage.getItem(TOKEN_KEY)
    const raw   = localStorage.getItem(USER_KEY)
    const user  = raw ? (JSON.parse(raw) as UserOut) : null
    if (token) setToken(token)
    return { token, user }
  } catch {
    return { token: null, user: null }
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const persisted = loadPersisted()
  const [token, setTokenState] = useState<string | null>(persisted.token)
  const [user,  setUser]       = useState<UserOut | null>(persisted.user)

  const login = useCallback(async (username: string, password: string) => {
    // ── Dev / offline credentials (no backend DB required) ──────────────────
    const DEV_USERS: Record<string, { password: string; roles: string[] }> = {
      admin:    { password: 'admin123',    roles: ['ADMIN'] },
      operator: { password: 'operator123', roles: ['OPERATOR'] },
      crew:     { password: 'crew123',     roles: ['CREW'] },
      viewer:   { password: 'viewer123',   roles: ['VIEWER'] },
    }
    const devUser = DEV_USERS[username.toLowerCase()]
    if (devUser && devUser.password === password) {
      const header  = btoa(JSON.stringify({ alg: 'none', typ: 'JWT' }))
      const payload = btoa(JSON.stringify({ sub: username, uname: username, roles: devUser.roles }))
      const devToken = `${header}.${payload}.dev_signature`
      const devUserObj: UserOut = {
        user_id:   username,
        username,
        email:     `${username}@ncpor.res.in`,
        roles:     devUser.roles,
        is_active: true,
      }
      setToken(devToken)
      setTokenState(devToken)
      setUser(devUserObj)
      localStorage.setItem(TOKEN_KEY, devToken)
      localStorage.setItem(USER_KEY,  JSON.stringify(devUserObj))
      return
    }

    // ── Production: real backend ─────────────────────────────────────────────
    const resp = await apiLogin(username, password)
    let userObj: UserOut = { user_id: '', username, email: username, roles: [], is_active: true }
    try {
      const p = JSON.parse(atob(resp.access_token.split('.')[1]))
      userObj = {
        user_id:   p.sub ?? '',
        username:  p.uname ?? username,
        email:     p.uname ?? username,
        roles:     p.roles ?? [],
        is_active: true,
      }
    } catch { /* keep default */ }

    setToken(resp.access_token)
    setTokenState(resp.access_token)
    setUser(userObj)
    localStorage.setItem(TOKEN_KEY, resp.access_token)
    localStorage.setItem(USER_KEY,  JSON.stringify(userObj))
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setTokenState(null)
    setUser(null)
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }, [])

  return (
    <AuthContext.Provider value={{ token, user, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
