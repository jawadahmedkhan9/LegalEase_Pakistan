"use client"

import { useState, useEffect, useRef } from "react"
import ReactMarkdown from "react-markdown"
import "./App.css"

const API_BASE_URL = process.env.REACT_APP_API_URL !== undefined ? process.env.REACT_APP_API_URL : "http://localhost:8000"
const REQUEST_TIMEOUT = 60000
const MAX_MESSAGE_LENGTH = 5000
const MAX_FILE_SIZE = 10 * 1024 * 1024

const formatConversationHistory = (messages) =>
  messages.filter((m) => m.role === "user" || m.role === "assistant").map((m) => ({ role: m.role, content: m.content }))

const fetchWithTimeout = async (url, options, timeout = REQUEST_TIMEOUT) => {
  const controller = new AbortController()
  const id = setTimeout(() => controller.abort(), timeout)
  try {
    const res = await fetch(url, { ...options, signal: controller.signal })
    clearTimeout(id)
    return res
  } catch (err) {
    clearTimeout(id)
    if (err.name === "AbortError") throw new Error("Request timeout. Please try again.")
    throw err
  }
}

const parseErrorResponse = async (res) => {
  try {
    const d = await res.json()
    return d.detail || d.message || `HTTP error! status: ${res.status}`
  } catch {
    return `HTTP error! status: ${res.status}`
  }
}

// ── AUTH HELPER ──────────────────────────────────────────────────────────────
const authHelper = {
  hashPassword: (p) => {
    let h = 0
    for (let i = 0; i < p.length; i++) { const c = p.charCodeAt(i); h = ((h << 5) - h) + c; h = h & h }
    return h.toString(36)
  },
  getUsers: () => { try { const u = localStorage.getItem("legalease_users"); return u ? JSON.parse(u) : {} } catch { return {} } },
  saveUsers: (u) => { try { localStorage.setItem("legalease_users", JSON.stringify(u)) } catch {} },
  register: (email, password, name) => {
    const users = authHelper.getUsers()
    const emailLower = email.toLowerCase().trim()
    if (users[emailLower]) throw new Error("Email already registered")
    if (!emailLower.includes("@") || !emailLower.includes(".")) throw new Error("Invalid email format")
    if (password.length < 6) throw new Error("Password must be at least 6 characters")
    const userId = Date.now().toString() + Math.random().toString(36).substr(2, 9)
    users[emailLower] = { id: userId, email: emailLower, name: name.trim(), passwordHash: authHelper.hashPassword(password), createdAt: new Date().toISOString() }
    authHelper.saveUsers(users)
    return { success: true, message: "Registration successful" }
  },
  login: (email, password) => {
    const users = authHelper.getUsers()
    const emailLower = email.toLowerCase().trim()
    if (!users[emailLower]) throw new Error("Invalid email or password")
    const user = users[emailLower]
    if (user.passwordHash !== authHelper.hashPassword(password)) throw new Error("Invalid email or password")
    const token = Date.now().toString() + Math.random().toString(36).substr(2, 16)
    const sessionData = { user_id: user.id, email: emailLower, created_at: new Date().toISOString(), expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString() }
    localStorage.setItem("legalease_session_token", token)
    localStorage.setItem("legalease_session_data", JSON.stringify(sessionData))
    return { success: true, session_token: token, user: { id: user.id, email: emailLower, name: user.name } }
  },
  checkSession: () => {
    try {
      const token = localStorage.getItem("legalease_session_token")
      const sd = localStorage.getItem("legalease_session_data")
      if (!token || !sd) return { authenticated: false, user: null }
      const sessionData = JSON.parse(sd)
      if (new Date() > new Date(sessionData.expires_at)) { authHelper.logout(); return { authenticated: false, user: null } }
      const users = authHelper.getUsers()
      const user = users[sessionData.email]
      if (!user) { authHelper.logout(); return { authenticated: false, user: null } }
      return { authenticated: true, user: { id: user.id, email: user.email, name: user.name } }
    } catch { return { authenticated: false, user: null } }
  },
  logout: () => {
    localStorage.removeItem("legalease_session_token")
    localStorage.removeItem("legalease_session_data")
    localStorage.removeItem("legalease_user")
  },
}

// ── API SERVICE ──────────────────────────────────────────────────────────────
const apiService = {
  sendChatMessage: async (message, conversationHistory, documentContext = null, documentName = null) => {
    const res = await fetchWithTimeout(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversation_history: formatConversationHistory(conversationHistory), document_context: documentContext, document_name: documentName }),
    })
    if (!res.ok) throw new Error(await parseErrorResponse(res))
    return res.json()
  },
  extractDocument: async (file) => {
    const formData = new FormData()
    formData.append("file", file)
    const res = await fetchWithTimeout(`${API_BASE_URL}/extract-document`, { method: "POST", body: formData }, REQUEST_TIMEOUT * 2)
    if (!res.ok) throw new Error(await parseErrorResponse(res))
    return res.json()
  },
  analyzeContract: async (file) => {
    const formData = new FormData()
    formData.append("file", file)
    const res = await fetchWithTimeout(`${API_BASE_URL}/analyze-contract`, { method: "POST", body: formData }, REQUEST_TIMEOUT * 2)
    if (!res.ok) throw new Error(await parseErrorResponse(res))
    return res.json()
  },
  register: async (email, password, name) => new Promise((res, rej) => { try { res(authHelper.register(email, password, name)) } catch (e) { rej(e) } }),
  login: async (email, password) => new Promise((res, rej) => { try { res(authHelper.login(email, password)) } catch (e) { rej(e) } }),
  logout: async () => { authHelper.logout(); return { success: true } },
  checkSession: async () => authHelper.checkSession(),
}

// ── CHAT HISTORY ─────────────────────────────────────────────────────────────
let saveTimeout = null
const chatHistoryHelper = {
  saveChat: (messages) => {
    if (saveTimeout) clearTimeout(saveTimeout)
    saveTimeout = setTimeout(() => {
      try {
        const chatHistory = { messages, timestamp: new Date().toISOString(), id: Date.now() }
        localStorage.setItem("legalease_current_chat", JSON.stringify(chatHistory))
        const allChats = JSON.parse(localStorage.getItem("legalease_chat_history") || "[]")
        const existingIndex = allChats.findIndex((c) => c.messages.length === messages.length && c.messages[c.messages.length - 1]?.content === messages[messages.length - 1]?.content)
        if (existingIndex >= 0) allChats[existingIndex] = chatHistory
        else allChats.push(chatHistory)
        if (allChats.length > 50) allChats.shift()
        localStorage.setItem("legalease_chat_history", JSON.stringify(allChats))
      } catch {}
    }, 1000)
  },
  loadCurrentChat: () => { try { const s = localStorage.getItem("legalease_current_chat"); return s ? JSON.parse(s).messages : [] } catch { return [] } },
  clearCurrentChat: () => localStorage.removeItem("legalease_current_chat"),
  getStoredChats: () => { try { return JSON.parse(localStorage.getItem("legalease_chat_history") || "[]") } catch { return [] } },
}

// ── DUMMY DATA ───────────────────────────────────────────────────────────────
// LAWYERS array removed — data is now fetched live from /api/lawyers

// ── ICONS ────────────────────────────────────────────────────────────────────
const Ic = {
  Scale: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" /></svg>,
  Chat: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>,
  File: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>,
  Users: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" /></svg>,
  BookOpen: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.246 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>,
  Home: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg>,
  Globe: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" /></svg>,
  User: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>,
  Send: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" /></svg>,
  Paperclip: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6" /></svg>,
  Mic: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>,
  Upload: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>,
  X: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>,
  Menu: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>,
  Trash: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>,
  AlertTriangle: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.464 0L4.35 16.5c-.77.833.192 2.5 1.732 2.5z" /></svg>,
  CheckCircle: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
  Download: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>,
  Share: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" /></svg>,
  Search: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>,
  Filter: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" /></svg>,
  MapPin: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" /></svg>,
  Clock: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
  MessageSq: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>,
  Phone: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" /></svg>,
  Play: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
  Book: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.246 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>,
  Vol: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" /></svg>,
  Camera: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" /></svg>,
  LogOut: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>,
  NearMe: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>,
  Copy: () => <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="100%" height="100%"><rect x="9" y="9" width="13" height="13" rx="2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>,
}

// ── TOP NAV ──────────────────────────────────────────────────────────────────
const NAV_ITEMS = [
  { id: "home", label: "Home", icon: "Home" },
  { id: "chat", label: "AI Chat", icon: "Chat" },
  { id: "document", label: "Document Analyzer", icon: "File" },
  { id: "lawyers", label: "Find Lawyers", icon: "Users" },
  { id: "education", label: "Legal Education", icon: "BookOpen" },
]

const TopNav = ({ activePage, setActivePage, user, onLogout }) => {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [lang, setLang] = useState("EN")

  return (
    <>
      <nav className="top-nav">
        <div className="nav-logo" style={{ cursor: "pointer" }} onClick={() => setActivePage("home")}>
          <div className="nav-logo-icon"><Ic.Scale /></div>
          <span>LegalEase Pakistan</span>
        </div>
        <div className="nav-items">
          {NAV_ITEMS.map((item) => {
            const Icon = Ic[item.icon]
            return (
              <button key={item.id} className={`nav-item-btn ${activePage === item.id ? "active" : ""}`} onClick={() => setActivePage(item.id)}>
                <Icon />{item.label}
              </button>
            )
          })}
        </div>
        <div className="nav-right">
          <button className="nav-lang-btn" onClick={() => setLang(lang === "EN" ? "اُر" : "EN")}>
            <Ic.Globe /><span>{lang}</span>
          </button>
          {user && (
            <button className="nav-user-btn" onClick={() => setActivePage("profile")}>
              <div className="nav-avatar">{user.name ? user.name[0].toUpperCase() : "U"}</div>
              <span>{user.name?.split(" ")[0]}</span>
            </button>
          )}
          <button className="nav-mobile-menu-btn" onClick={() => setMobileOpen(true)}><Ic.Menu /></button>
        </div>
      </nav>
      {mobileOpen && (
        <div className="mobile-nav-overlay open" onClick={() => setMobileOpen(false)}>
          <div className="mobile-nav-panel" onClick={(e) => e.stopPropagation()}>
            <div className="mobile-nav-header">
              <div className="nav-logo"><div className="nav-logo-icon"><Ic.Scale /></div><span>LegalEase</span></div>
              <button onClick={() => setMobileOpen(false)} style={{ color: "var(--text-muted)", display: "flex" }}><Ic.X /></button>
            </div>
            {NAV_ITEMS.map((item) => {
              const Icon = Ic[item.icon]
              return (
                <button key={item.id} className={`mobile-nav-item ${activePage === item.id ? "active" : ""}`} onClick={() => { setActivePage(item.id); setMobileOpen(false) }}>
                  <Icon />{item.label}
                </button>
              )
            })}
            <div style={{ marginTop: "auto", paddingTop: "1rem", borderTop: "1px solid var(--border)" }}>
              <button className="mobile-nav-item" onClick={() => { onLogout(); setMobileOpen(false) }} style={{ color: "var(--red)" }}>
                <Ic.LogOut />Sign Out
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// ── AUTH PAGE ────────────────────────────────────────────────────────────────
const AuthPage = ({ onLoginSuccess }) => {
  const [tab, setTab] = useState("login")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [name, setName] = useState("")
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    setError(null); setSuccess(null); setLoading(true)
    try {
      if (tab === "login") {
        const res = await apiService.login(email, password)
        if (res.success && res.session_token) onLoginSuccess(res.user, res.session_token)
      } else {
        const res = await apiService.register(email, password, name)
        if (res.success) { setSuccess("Account created! Please login."); setTab("login"); setName(""); setPassword("") }
      }
    } catch (e) { setError(e.message || "An error occurred.") }
    finally { setLoading(false) }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">
          <div className="auth-logo-icon"><Ic.Scale /></div>
          <h1>LegalEase Pakistan</h1>
        </div>
        <p className="auth-tagline">Your AI-Powered Legal Assistant for Pakistani Law</p>
        <div className="auth-tabs">
          <button className={`auth-tab ${tab === "login" ? "active" : ""}`} onClick={() => { setTab("login"); setError(null); setSuccess(null) }}>Login</button>
          <button className={`auth-tab ${tab === "signup" ? "active" : ""}`} onClick={() => { setTab("signup"); setError(null); setSuccess(null) }}>Sign Up</button>
        </div>
        <div className="auth-form">
          {error && <div className="auth-alert error">{error}</div>}
          {success && <div className="auth-alert success">{success}</div>}
          {tab === "signup" && (
            <div className="form-group">
              <label>Full Name</label>
              <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Enter your full name" disabled={loading} />
            </div>
          )}
          <div className="form-group">
            <label>Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Enter your email" disabled={loading} />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter your password" onKeyDown={(e) => { if (e.key === "Enter") handleSubmit() }} disabled={loading} />
            {tab === "signup" && <span className="form-hint">Minimum 6 characters</span>}
          </div>
          <button className="btn-primary" onClick={handleSubmit} disabled={loading}>
            {loading ? "Please wait..." : tab === "login" ? "Login" : "Create Account"}
          </button>
        </div>
        <div className="auth-features">
          {[["Chat","AI Chatbot"],["File","Doc Analysis"],["Scale","Pak Law"]].map(([icon, label]) => {
            const Icon = Ic[icon]
            return <div key={label} className="auth-feature"><Icon /><span>{label}</span></div>
          })}
        </div>
      </div>
    </div>
  )
}

// ── ANIMATED COUNTER ─────────────────────────────────────────────────────────
const AnimatedCounter = ({ target, suffix = "", duration = 2000 }) => {
  const [count, setCount] = useState(0)
  const ref = useRef(null)
  const started = useRef(false)
  useEffect(() => {
    const obs = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !started.current) {
        started.current = true
        const isFloat = String(target).includes(".")
        const num = parseFloat(target)
        const steps = 60
        const step = num / steps
        let cur = 0
        const timer = setInterval(() => {
          cur += step
          if (cur >= num) { cur = num; clearInterval(timer) }
          setCount(isFloat ? parseFloat(cur.toFixed(1)) : Math.floor(cur))
        }, duration / steps)
      }
    }, { threshold: 0.3 })
    if (ref.current) obs.observe(ref.current)
    return () => obs.disconnect()
  }, [target, duration])
  return <span ref={ref}>{count}{suffix}</span>
}

// ── HOME PAGE ────────────────────────────────────────────────────────────────
const TICKER_ITEMS = [
  "⚖️  Family Law","🏠  Property Rights","🏦  Banking Law",
  "👮  Criminal Defense","📋  Contract Law","🕌  Religious Law",
  "👷  Labor Rights","🌐  Cyber Law","📜  Constitutional Rights",
  "💼  Corporate Law","🧑‍⚖️  Court Procedures","📑  FIR Guidance",
]

const FEATURES = [
  { icon:"Chat",     title:"AI Legal Chatbot",   desc:"Instant answers in Urdu & English powered by Pakistani law databases",    page:"chat",      color:"#10B981", bg:"#D1FAE5", label:"Most Used" },
  { icon:"File",     title:"Document Analyzer",  desc:"Upload FIRs, contracts & property papers for AI risk assessment",          page:"document",  color:"#3B82F6", bg:"#DBEAFE", label:"" },
  { icon:"Users",    title:"Find Lawyers",        desc:"Connect with 1000+ verified legal professionals across Pakistan",          page:"lawyers",   color:"#8B5CF6", bg:"#EDE9FE", label:"" },
  { icon:"BookOpen", title:"Legal Education",     desc:"Learn Pakistani law through interactive courses & real case studies",       page:"education", color:"#F59E0B", bg:"#FEF3C7", label:"New" },
]

const HOW_STEPS = [
  { num:"01", title:"Ask a Question",   desc:"Type in Urdu or English — our AI understands both languages fluently",       icon:"Chat"  },
  { num:"02", title:"Upload Documents", desc:"FIRs, contracts, property papers — AI analyzes them in seconds",              icon:"File"  },
  { num:"03", title:"Get Guidance",     desc:"Clear, actionable legal advice backed by Pakistani law databases",            icon:"Scale" },
  { num:"04", title:"Connect a Lawyer", desc:"One tap to reach a verified lawyer for professional representation",          icon:"Users" },
]

const HomePage = ({ setActivePage }) => {
  const [mouse, setMouse] = useState({ x: 50, y: 50 })
  const [visible, setVisible] = useState(false)
  const heroRef = useRef(null)

  useEffect(() => {
    setTimeout(() => setVisible(true), 60)
    const el = heroRef.current
    if (!el) return
    const onMove = (e) => {
      const r = el.getBoundingClientRect()
      setMouse({ x: ((e.clientX - r.left) / r.width) * 100, y: ((e.clientY - r.top) / r.height) * 100 })
    }
    el.addEventListener("mousemove", onMove)
    return () => el.removeEventListener("mousemove", onMove)
  }, [])

  return (
    <div className="page-enter hp-page">

      {/* ══ HERO ══ */}
      <section className="hp-hero" ref={heroRef}>
        {/* Animated gradient orbs */}
        <div className="hp-orb hp-orb-a" style={{ transform: `translate(${mouse.x * 0.06}px, ${mouse.y * 0.04}px)` }} />
        <div className="hp-orb hp-orb-b" style={{ transform: `translate(${mouse.x * -0.04}px, ${mouse.y * 0.03}px)` }} />
        <div className="hp-orb hp-orb-c" style={{ transform: `translate(${mouse.x * 0.02}px, ${mouse.y * -0.05}px)` }} />
        {/* Grid overlay */}
        <svg className="hp-grid-svg" preserveAspectRatio="xMidYMid slice" viewBox="0 0 1200 500">
          {[...Array(11)].map((_,i) => <line key={`v${i}`} x1={i*120} y1="0" x2={i*120} y2="500" stroke="rgba(255,255,255,0.055)" strokeWidth="1"/>)}
          {[...Array(6)].map((_,i)  => <line key={`h${i}`} x1="0" y1={i*100} x2="1200" y2={i*100} stroke="rgba(255,255,255,0.055)" strokeWidth="1"/>)}
        </svg>

        <div className={`hp-hero-inner ${visible ? "hp-in" : ""}`}>
          {/* LEFT */}
          <div className="hp-hero-left">
            <div className="hp-badge">
              <span className="hp-badge-dot" />
              AI-Powered Legal Assistance
            </div>
            <h1 className="hp-h1">
              Legal Justice<br />
              for <span className="hp-h1-em">Every Pakistani</span>
            </h1>
            <p className="hp-hero-sub">
              Access professional legal guidance, analyze documents, and connect with verified lawyers — in your language, at your fingertips.
            </p>
            <div className="hp-trust-strip">
              {["✓ Free to Use","✓ Urdu & English","✓ 1000+ Lawyers","✓ 24 / 7 AI"].map(t=>(
                <span key={t} className="hp-trust-pill">{t}</span>
              ))}
            </div>
            <div className="hp-hero-btns">
              <button className="hp-btn-white" onClick={() => setActivePage("chat")}>
                <Ic.Chat />Start AI Chat
              </button>
              <button className="hp-btn-ghost" onClick={() => setActivePage("document")}>
                <Ic.File />Analyze Document
              </button>
            </div>
          </div>

          {/* RIGHT — Justice Card */}
          <div className="hp-hero-right">
            <div className="hp-justice-card">
              <svg className="hp-scales-svg" width="160" height="148" viewBox="0 0 140 128" fill="none">
                <rect x="58" y="104" width="24" height="16" rx="3" fill="rgba(255,255,255,0.25)" stroke="rgba(255,255,255,0.4)" strokeWidth="1.5"/>
                <rect x="46" y="116" width="48" height="6" rx="3" fill="rgba(255,255,255,0.28)" stroke="rgba(255,255,255,0.4)" strokeWidth="1.5"/>
                <line x1="70" y1="14" x2="70" y2="104" stroke="rgba(255,255,255,0.8)" strokeWidth="2.5" strokeLinecap="round"/>
                <circle cx="70" cy="12" r="7" fill="rgba(255,255,255,0.9)"/>
                <circle cx="70" cy="12" r="4" fill="#7fffd4"/>
                <line x1="22" y1="38" x2="118" y2="38" stroke="rgba(255,255,255,0.7)" strokeWidth="2.5" strokeLinecap="round"/>
                <g className="hp-pan-l">
                  <line x1="32" y1="38" x2="32" y2="62" stroke="rgba(255,255,255,0.65)" strokeWidth="1.5" strokeLinecap="round" strokeDasharray="3 2"/>
                  <path d="M18 62 Q32 74 46 62" stroke="rgba(127,255,212,0.9)" strokeWidth="2" fill="rgba(127,255,212,0.2)" strokeLinecap="round"/>
                  <ellipse cx="32" cy="62" rx="14" ry="4" fill="rgba(127,255,212,0.2)" stroke="rgba(127,255,212,0.8)" strokeWidth="1.5"/>
                </g>
                <g className="hp-pan-r">
                  <line x1="108" y1="38" x2="108" y2="54" stroke="rgba(255,255,255,0.6)" strokeWidth="1.5" strokeLinecap="round" strokeDasharray="3 2"/>
                  <path d="M94 54 Q108 66 122 54" stroke="rgba(255,255,255,0.65)" strokeWidth="2" fill="rgba(255,255,255,0.09)" strokeLinecap="round"/>
                  <ellipse cx="108" cy="54" rx="14" ry="4" fill="rgba(255,255,255,0.09)" stroke="rgba(255,255,255,0.5)" strokeWidth="1.5"/>
                </g>
                <circle cx="20"  cy="24" r="2"   fill="rgba(255,255,255,0.5)"  className="hp-twinkle"/>
                <circle cx="118" cy="20" r="1.5" fill="rgba(127,255,212,0.7)" className="hp-twinkle" style={{animationDelay:"0.6s"}}/>
                <circle cx="8"   cy="56" r="1.5" fill="rgba(255,255,255,0.35)" className="hp-twinkle" style={{animationDelay:"1.1s"}}/>
                <circle cx="132" cy="68" r="1.5" fill="rgba(255,255,255,0.3)"  className="hp-twinkle" style={{animationDelay:"1.7s"}}/>
              </svg>
              <div className="hp-justice-word">JUSTICE</div>
              <p className="hp-justice-sub">Legal Aid for Pakistan</p>
              <div className="hp-online-pill">
                <span className="hp-online-dot" />
                AI Online · ~30s response
              </div>
            </div>

            {/* Floating stat chips around the card */}
            <div className="hp-float-chip hp-chip-1"><span className="hp-chip-num">1000+</span><span className="hp-chip-lbl">Verified Lawyers</span></div>
            <div className="hp-float-chip hp-chip-2"><span className="hp-chip-num">24/7</span><span className="hp-chip-lbl">AI Available</span></div>
            <div className="hp-float-chip hp-chip-3"><span className="hp-chip-num">98%</span><span className="hp-chip-lbl">Satisfaction</span></div>
          </div>
        </div>
      </section>

      {/* ══ TICKER ══ */}
      <div className="hp-ticker">
        <div className="hp-ticker-inner">
          {[...TICKER_ITEMS,...TICKER_ITEMS].map((t,i) => (
            <span key={i} className="hp-tick">{t}<span className="hp-tick-sep">·</span></span>
          ))}
        </div>
      </div>

      {/* ══ STATS + FEATURES merged section ══ */}
      <section className="hp-mid-section">
        {/* Stats row — full width, edge to edge */}
        <div className="hp-stats-row">
          <div className="hp-stat-block hp-stat-red">
            <div className="hp-stat-icon-box" style={{background:"#FEE2E2"}}>
              <svg fill="none" stroke="#EF4444" viewBox="0 0 24 24" width="20" height="20"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
            </div>
            <div className="hp-stat-num" style={{color:"#EF4444"}}><AnimatedCounter target={98.2} suffix="%" /></div>
            <div className="hp-stat-lbl">Cannot Access Justice</div>
            <div className="hp-stat-desc">of Pakistani citizens lack proper legal representation</div>
          </div>
          <div className="hp-stat-divider" />
          <div className="hp-stat-block hp-stat-green">
            <div className="hp-stat-icon-box" style={{background:"#D1FAE5"}}>
              <svg fill="none" stroke="#10B981" viewBox="0 0 24 24" width="20" height="20"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            </div>
            <div className="hp-stat-num" style={{color:"#10B981"}}>24 / 7</div>
            <div className="hp-stat-lbl">AI Assistance</div>
            <div className="hp-stat-desc">Round-the-clock legal guidance in English and Urdu</div>
          </div>
          <div className="hp-stat-divider" />
          <div className="hp-stat-block hp-stat-blue">
            <div className="hp-stat-icon-box" style={{background:"#DBEAFE"}}>
              <svg fill="none" stroke="#3B82F6" viewBox="0 0 24 24" width="20" height="20"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
            </div>
            <div className="hp-stat-num" style={{color:"#3B82F6"}}><AnimatedCounter target={1000} suffix="+" /></div>
            <div className="hp-stat-lbl">Verified Lawyers</div>
            <div className="hp-stat-desc">Qualified legal professionals across Pakistan</div>
          </div>
        </div>

        {/* Features — 4 col full width */}
        <div className="hp-features-wrap">
          <div className="hp-section-head">
            <h2 className="hp-section-title">Everything You Need, In One Place</h2>
            <p className="hp-section-sub">AI-powered tools built for Pakistani law and Pakistani people</p>
          </div>
          <div className="hp-features-grid">
            {FEATURES.map(({ icon, title, desc, page, color, bg, label }) => {
              const Icon = Ic[icon]
              return (
                <div key={title} className="hp-feat-card" onClick={() => setActivePage(page)} style={{"--fc": color, "--fb": bg}}>
                  {label && <span className="hp-feat-label" style={{background: color}}>{label}</span>}
                  <div className="hp-feat-icon" style={{background: bg}}>
                    <div style={{color, width:22, height:22}}><Icon /></div>
                  </div>
                  <h3 className="hp-feat-title">{title}</h3>
                  <p className="hp-feat-desc">{desc}</p>
                  <div className="hp-feat-cta" style={{color}}>
                    Explore
                    <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M17 8l4 4m0 0l-4 4m4-4H3"/></svg>
                  </div>
                  <div className="hp-feat-glow" style={{background:`radial-gradient(ellipse at 100% 100%, ${color}20 0%, transparent 65%)`}} />
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* ══ HOW IT WORKS ══ */}
      <section className="hp-how-section">
        <div className="hp-section-head">
          <h2 className="hp-section-title">From Question to Resolution</h2>
          <p className="hp-section-sub">Four simple steps to get the legal help you deserve</p>
        </div>
        <div className="hp-how-grid">
          {HOW_STEPS.map(({ num, title, desc, icon }, i) => {
            const Icon = Ic[icon]
            return (
              <div key={num} className="hp-how-card">
                <div className="hp-how-step">{num}</div>
                <div className="hp-how-icon"><Icon /></div>
                <h3 className="hp-how-title">{title}</h3>
                <p className="hp-how-desc">{desc}</p>
                {i < HOW_STEPS.length - 1 && <div className="hp-how-line" />}
              </div>
            )
          })}
        </div>
      </section>

      {/* ══ CTA ══ */}
      <section className="hp-cta">
        <div className="hp-cta-ring hp-cta-ring-1" />
        <div className="hp-cta-ring hp-cta-ring-2" />
        <div className="hp-cta-ring hp-cta-ring-3" />
        <div className="hp-cta-body">
          <span className="hp-cta-pill">Free · No Hidden Fees · No Sign-Up Required</span>
          <h2 className="hp-cta-h2">Your Rights Are Worth<br />Fighting For.</h2>
          <p className="hp-cta-p">Join thousands of Pakistanis who access justice through LegalEase every day.</p>
          <div className="hp-cta-btns">
            <button className="hp-btn-white hp-cta-main" onClick={() => setActivePage("chat")}>
              <Ic.Chat />Get Free Legal Advice
            </button>
            <button className="hp-btn-ghost hp-cta-sec" onClick={() => setActivePage("lawyers")}>
              <Ic.Users />Find a Lawyer
            </button>
          </div>
        </div>
      </section>

    </div>
  )
}

// ── CITATION LINK ────────────────────────────────────────────────────────────
const CitationLink = ({ source, index }) => {
  const handleClick = (e) => {
    if (source.url) return
    e.preventDefault()
    window.open(`https://pakistancode.gov.pk/search?q=${encodeURIComponent((source.title || "") + " " + (source.source || ""))}`, "_blank")
  }
  return (
    <a href={source.url || "#"} target={source.url ? "_blank" : "_self"} rel="noreferrer" className="source-chip" onClick={handleClick}>
      [{index}] {(source.title || "").slice(0, 30)}{(source.title || "").length > 30 ? "…" : ""}
    </a>
  )
}

// ── CHAT MESSAGE ─────────────────────────────────────────────────────────────
const ChatMessage = ({ message }) => {
  const [showAll, setShowAll] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const isBot = message.role === "assistant"

  const ts = (t) => {
    if (!t) return ""
    const diff = Math.floor((new Date() - new Date(t)) / 60000)
    if (diff < 1) return "Just now"
    if (diff < 60) return diff + "m ago"
    if (diff < 1440) return Math.floor(diff / 60) + "h ago"
    return new Date(t).toLocaleDateString()
  }

  const handleSpeak = () => {
    if (isSpeaking) { window.speechSynthesis.cancel(); setIsSpeaking(false); return }
    const u = new SpeechSynthesisUtterance(message.content)
    u.rate = 0.9
    u.onstart = () => setIsSpeaking(true)
    u.onend = () => setIsSpeaking(false)
    u.onerror = () => setIsSpeaking(false)
    window.speechSynthesis.speak(u)
  }

  const sources = message.sources || []
  const shown = showAll ? sources : sources.slice(0, 3)

  return (
    <div className={`message-row${isBot ? "" : " user"}`}>
      <div className={`msg-avatar ${isBot ? "bot" : "user-av"}`}>{isBot ? <Ic.Scale /> : <Ic.User />}</div>
      <div className="msg-bubble-wrap">
        {message.hasAttachment && message.attachmentName && (
          <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.375rem" }}>
            <Ic.File /><span>{message.attachmentName}</span>
          </div>
        )}
        <div className={`msg-bubble ${isBot ? "bot" : "user-msg"}`}>
          {isBot ? <div className="markdown-content"><ReactMarkdown>{message.content}</ReactMarkdown></div> : message.content}
          {sources.length > 0 && (
            <div className="msg-sources">
              <div className="msg-sources-label"><Ic.File /><span>Legal References ({sources.length})</span></div>
              <div>{shown.map((s, i) => <CitationLink key={i} source={s} index={s.citation_number || i + 1} />)}</div>
              {sources.length > 3 && (
                <button onClick={() => setShowAll(!showAll)} style={{ fontSize: "0.75rem", color: "var(--primary)", marginTop: "0.375rem" }}>
                  {showAll ? "Show less" : `+${sources.length - 3} more sources`}
                </button>
              )}
            </div>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span className="msg-time">{ts(message.timestamp)}</span>
          {isBot && (
            <>
              <button className={`chat-input-action-btn${isSpeaking ? " listening" : ""}`} onClick={handleSpeak} title="Read aloud" style={{ width: 22, height: 22 }}><Ic.Vol /></button>
              <button className="chat-input-action-btn" onClick={() => navigator.clipboard.writeText(message.content)} title="Copy" style={{ width: 22, height: 22 }}><Ic.Copy /></button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── AI CHAT PAGE ─────────────────────────────────────────────────────────────
const ChatPage = ({ setActivePage }) => {
  const [input, setInput] = useState("")
  const [messages, setMessages] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [attachedDoc, setAttachedDoc] = useState(null)
  const [isExtracting, setIsExtracting] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const messagesEndRef = useRef(null)
  const fileInputRef = useRef(null)
  const cameraInputRef = useRef(null)
  const recognitionRef = useRef(null)

  useEffect(() => {
    const saved = chatHistoryHelper.loadCurrentChat()
    if (saved.length > 0) setMessages(saved)
    if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition
      recognitionRef.current = new SR()
      recognitionRef.current.continuous = false
      recognitionRef.current.interimResults = false
      recognitionRef.current.lang = "en-US"
      recognitionRef.current.onresult = (e) => setInput((prev) => prev + (prev ? " " : "") + e.results[0][0].transcript)
      recognitionRef.current.onerror = () => setIsListening(false)
      recognitionRef.current.onend = () => setIsListening(false)
    }
  }, [])

  useEffect(() => { if (messages.length > 0) chatHistoryHelper.saveChat(messages) }, [messages])
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }) }, [messages, isLoading])

  const handleFileSelect = async (file) => {
    if (!file) return
    const validTypes = ["image/jpeg","image/jpg","image/png","image/webp","application/pdf","application/vnd.openxmlformats-officedocument.wordprocessingml.document","text/plain"]
    if (!validTypes.includes(file.type)) { setError("Invalid file type."); setTimeout(() => setError(null), 4000); return }
    if (file.size > MAX_FILE_SIZE) { setError("File too large (max 10MB)."); setTimeout(() => setError(null), 4000); return }
    const isImage = file.type.startsWith("image/")
    const previewUrl = isImage ? URL.createObjectURL(file) : null
    setIsExtracting(true)
    setAttachedDoc({ name: file.name, extractedText: null, charCount: 0, isImage, previewUrl })
    try {
      const result = await apiService.extractDocument(file)
      if (!result.success) throw new Error(result.message)
      const extractedText = result.extracted_text ? result.extracted_text.trim() : ""
      setAttachedDoc({ name: file.name, extractedText, charCount: extractedText.length, isImage, previewUrl })
    } catch (err) {
      setError(err.message || "Failed to extract document.")
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      setAttachedDoc(null)
      setTimeout(() => setError(null), 4000)
    } finally {
      setIsExtracting(false)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  const removeAttachment = () => {
    if (attachedDoc?.previewUrl) URL.revokeObjectURL(attachedDoc.previewUrl)
    setAttachedDoc(null)
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  const handleVoiceInput = () => {
    if (!recognitionRef.current) { setError("Speech recognition not supported."); return }
    if (isListening) { recognitionRef.current.stop(); setIsListening(false) }
    else { try { recognitionRef.current.start(); setIsListening(true) } catch { setError("Failed to start microphone.") } }
  }

  const handleSend = async () => {
    if ((!input.trim() && !attachedDoc) || isLoading || isExtracting) return
    if (attachedDoc && !attachedDoc.extractedText) {
      setError("No extractable text was found in the uploaded image. Please upload a clearer image or choose a different file.")
      setTimeout(() => setError(null), 5000)
      return
    }
    const msg = input.trim()
    const docToSend = attachedDoc
    setInput(""); setIsLoading(true); setError(null)
    try {
      const response = await apiService.sendChatMessage(msg, messages, docToSend?.extractedText, docToSend?.name)
      const userMsg = { role: "user", content: msg, hasAttachment: !!docToSend, attachmentName: docToSend?.name, timestamp: new Date().toISOString() }
      const botMsg = { role: "assistant", content: response.response, sources: response.sources, timestamp: new Date().toISOString() }
      if (docToSend?.previewUrl) URL.revokeObjectURL(docToSend.previewUrl)
      setMessages((prev) => [...prev, userMsg, botMsg])
      setAttachedDoc(null)
    } catch (e) {
      if (e.name !== "AbortError") { setError(e.message || "Failed to send message."); setTimeout(() => setError(null), 5000) }
    } finally { setIsLoading(false) }
  }

  const handleClearChat = () => { setMessages([]); chatHistoryHelper.clearCurrentChat() }
  const storedChats = chatHistoryHelper.getStoredChats()
  const QUICK_TOPICS = ["Property Rights", "Family Law", "Criminal Defense", "Labor Rights", "Business Law", "Consumer Rights"]

  return (
    <div className="chat-page page-enter">
      <div className="chat-sidebar">
        <div className="chat-sidebar-section">
          <h3>Chat History</h3>
          <div className="chat-history-list">
            {messages.length > 0 && (
              <div className="chat-history-item active">
                <div className="chat-history-item-title">{(messages.find((m) => m.role === "user")?.content || "Current Chat").slice(0, 28)}…</div>
                <div className="chat-history-item-time">Active now</div>
              </div>
            )}
            {storedChats.slice(-3).reverse().map((chat, i) => (
              <div key={i} className="chat-history-item">
                <div className="chat-history-item-title">{(chat.messages?.find((m) => m.role === "user")?.content || "Chat").slice(0, 28)}…</div>
                <div className="chat-history-item-time">{new Date(chat.timestamp).toLocaleDateString()}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="chat-sidebar-section">
          <h3>Quick Topics</h3>
          <div className="quick-topics-list">
            {QUICK_TOPICS.map((t) => <button key={t} className="quick-topic-btn" onClick={() => setInput(t)}>{t}</button>)}
          </div>
        </div>
        <div className="chat-sidebar-section">
          <h3>Emergency Contact</h3>
          <button className="emergency-btn"><Ic.Phone />Call Legal Helpline</button>
        </div>
      </div>

      <div className="chat-main">
        <div className="chat-header">
          <div className="chat-header-info">
            <div className="chat-bot-avatar"><Ic.Scale /></div>
            <div>
              <div className="chat-bot-name">AI Legal Assistant</div>
              <div className="chat-bot-status"><div className="status-dot-green"></div><span>Online · Responds in ~30 seconds</span></div>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <div className="chat-header-lang"><Ic.Globe /><span>EN / اُر</span></div>
            <button className="btn-connect-lawyer" onClick={() => setActivePage("lawyers")}>Connect to Lawyer</button>
          </div>
        </div>

        {error && (
          <div className="error-banner"><span>{error}</span><button onClick={() => setError(null)}><Ic.X /></button></div>
        )}

        <div className="messages-area">
          {messages.length === 0 ? (
            <div className="chat-empty-state">
              <div className="chat-empty-icon"><Ic.Scale /></div>
              <h3>AI Legal Assistant</h3>
              <p>Ask me anything about Pakistani law — property rights, family law, criminal procedures, labor rights, and more.</p>
            </div>
          ) : (
            <>
              <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "0.75rem" }}>
                <button className="btn-clear-chat" onClick={handleClearChat}><Ic.Trash /><span>Clear Chat</span></button>
              </div>
              <div className="message-row">
                <div className="msg-avatar bot"><Ic.Scale /></div>
                <div className="msg-bubble-wrap">
                  <div className="msg-bubble bot">
                    <p>Hello! I'm your AI legal assistant. I can help you with Pakistani law questions, document analysis, and connecting you with lawyers. How can I help you today?</p>
                  </div>
                  <div className="msg-time">Start of conversation</div>
                </div>
              </div>
              {messages.map((m, i) => <ChatMessage key={i} message={m} />)}
            </>
          )}
          {isLoading && (
            <div className="message-row">
              <div className="msg-avatar bot"><Ic.Scale /></div>
              <div className="msg-bubble-wrap">
                <div className="msg-bubble bot"><div className="typing-dots"><span /><span /><span /></div></div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-bar">
          {messages.length > 0 && (
            <div className="chat-controls-row">
              <button className="btn-clear-chat" onClick={handleClearChat}><Ic.Trash /><span>Clear</span></button>
              {input.length > 0 && <span className="char-count">{input.length}/{MAX_MESSAGE_LENGTH}</span>}
            </div>
          )}
          {attachedDoc && (
            <div className="chat-attachment-preview">
              <div className="chat-attachment-info">
                <Ic.File />
                <span>{attachedDoc.name} {isExtracting ? "(processing…)" : `(${(attachedDoc.charCount || 0).toLocaleString()} chars)`}</span>
              </div>
              {attachedDoc.extractedText && !isExtracting && (
                <div className="chat-attachment-snippet">{attachedDoc.extractedText.slice(0, 220)}{attachedDoc.extractedText.length > 220 ? "…" : ""}</div>
              )}
              <button className="btn-remove-attach" onClick={removeAttachment} disabled={isExtracting}><Ic.X /></button>
            </div>
          )}
          <div className="chat-input-wrapper">
            <button className="chat-input-action-btn" onClick={() => fileInputRef.current?.click()} disabled={isLoading || isExtracting} title="Attach"><Ic.Paperclip /></button>
            <button className="chat-input-action-btn" onClick={() => cameraInputRef.current?.click()} disabled={isLoading || isExtracting} title="Camera"><Ic.Camera /></button>
            <textarea
              className="chat-input-field"
              value={input}
              onChange={(e) => { if (e.target.value.length <= MAX_MESSAGE_LENGTH) setInput(e.target.value) }}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend() } }}
              placeholder="Type your legal question..."
              disabled={isLoading || isExtracting}
              rows={1}
            />
            <input ref={fileInputRef} type="file" className="hidden" onChange={(e) => handleFileSelect(e.target.files[0])} accept=".pdf,.docx,.jpg,.jpeg,.png,.webp,.txt" />
            <input ref={cameraInputRef} type="file" className="hidden" onChange={(e) => handleFileSelect(e.target.files[0])} accept="image/*" capture="environment" />
            <button className={`chat-input-action-btn${isListening ? " listening" : ""}`} onClick={handleVoiceInput} disabled={isLoading || isExtracting} title="Voice"><Ic.Mic /></button>
            <button className="chat-send-btn" onClick={handleSend} disabled={isLoading || isExtracting || (!input.trim() && !(attachedDoc?.extractedText?.length > 0))}><Ic.Send /></button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── DOCUMENT PAGE ────────────────────────────────────────────────────────────

// ============================================================================
// ENHANCED DocumentPage — Drop-in replacement for the DocumentPage component
// in App.js (lines ~671–808)
//
// Paste this entire block replacing the existing DocumentPage const.
// No other changes needed in App.js.
// ============================================================================

const DocumentPage = () => {
  const [file, setFile] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [error, setError] = useState(null)
  const [dragActive, setDragActive] = useState(false)
  const [activeTab, setActiveTab] = useState("risks")
  const [expandedRisk, setExpandedRisk] = useState(null)
  const [expandedMissing, setExpandedMissing] = useState(null)
  const fileInputRef = useRef(null)

  // ── Severity helpers ────────────────────────────────────────────────────
  const SEV_COLOR = {
    critical: { bg: "#fff0f0", border: "#fca5a5", text: "#991b1b", badge: "#ef4444" },
    high:     { bg: "#fff7ed", border: "#fdba74", text: "#9a3412", badge: "#f97316" },
    medium:   { bg: "#fefce8", border: "#fde047", text: "#854d0e", badge: "#eab308" },
    low:      { bg: "#f0fdf4", border: "#86efac", text: "#166534", badge: "#22c55e" },
  }

  const RISK_LABEL = {
    critical: "Critical",
    high: "High",
    medium: "Medium",
    low: "Low"
  }

  const getSeverityOrder = (sev) => ({ critical: 0, high: 1, medium: 2, low: 3 }[sev] ?? 4)

  const getScoreColor = (score) => {
    if (score >= 75) return "#22c55e"
    if (score >= 50) return "#eab308"
    if (score >= 30) return "#f97316"
    return "#ef4444"
  }

  // ── Score dial (SVG) ───────────────────────────────────────────────────
  const ScoreDial = ({ score }) => {
    const r = 52
    const cx = 70, cy = 70
    // Arc from 135° to 405° (270° sweep)
    const pct = Math.max(0, Math.min(100, score)) / 100
    const color = getScoreColor(score)

    const polarToXY = (deg, radius) => {
      const rad = (deg - 90) * Math.PI / 180
      return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) }
    }
    const describeArc = (startDeg, endDeg, rad) => {
      const s = polarToXY(startDeg, rad)
      const e = polarToXY(endDeg, rad)
      const large = (endDeg - startDeg) > 180 ? 1 : 0
      return `M ${s.x} ${s.y} A ${rad} ${rad} 0 ${large} 1 ${e.x} ${e.y}`
    }
    const arcEnd = 135 + pct * 270
    return (
      <svg width="140" height="120" viewBox="0 0 140 120" style={{ display: "block" }}>
        <path d={describeArc(135, 405, r)} fill="none" stroke="var(--color-border-tertiary)" strokeWidth="10" strokeLinecap="round" />
        {score > 0 && (
          <path d={describeArc(135, arcEnd, r)} fill="none" stroke={color} strokeWidth="10" strokeLinecap="round" style={{ transition: "all 0.8s ease" }} />
        )}
        <text x={cx} y={cy + 6} textAnchor="middle" fontSize="22" fontWeight="500" fill={color}>{score}</text>
        <text x={cx} y={cy + 22} textAnchor="middle" fontSize="10" fill="var(--color-text-secondary)">/ 100</text>
        <text x={cx} y={cy + 36} textAnchor="middle" fontSize="9" fill="var(--color-text-secondary)">compliance</text>
      </svg>
    )
  }

  // ── Risk card ──────────────────────────────────────────────────────────
  const RiskCard = ({ risk, idx }) => {
    const isOpen = expandedRisk === idx
    const colors = SEV_COLOR[risk.severity] || SEV_COLOR.medium

    return (
      <div style={{
        border: `1px solid ${colors.border}`,
        borderLeft: `4px solid ${colors.badge}`,
        borderRadius: "10px",
        marginBottom: "10px",
        background: isOpen ? colors.bg : "var(--color-background-primary)",
        transition: "background 0.2s"
      }}>
        {/* Header row */}
        <div
          onClick={() => setExpandedRisk(isOpen ? null : idx)}
          style={{ display: "flex", alignItems: "center", gap: "10px", padding: "12px 14px", cursor: "pointer" }}
        >
          <span style={{
            fontSize: "10px", fontWeight: "500", padding: "2px 8px",
            borderRadius: "20px", background: colors.badge, color: "#fff",
            textTransform: "uppercase", letterSpacing: "0.5px", whiteSpace: "nowrap"
          }}>
            {RISK_LABEL[risk.severity]}
          </span>
          <span style={{ fontSize: "11px", color: "var(--color-text-secondary)", fontStyle: "italic" }}>
            {risk.category}
          </span>
          <span style={{ flex: 1, fontSize: "13px", fontWeight: "500", color: "var(--color-text-primary)" }}>
            {risk.title}
          </span>
          <span style={{ fontSize: "16px", color: "var(--color-text-secondary)", transform: isOpen ? "rotate(180deg)" : "rotate(0)", transition: "transform 0.2s" }}>▾</span>
        </div>

        {/* Expanded body */}
        {isOpen && (
          <div style={{ padding: "0 14px 14px", borderTop: `1px solid ${colors.border}` }}>
            <p style={{ margin: "10px 0 12px", fontSize: "13px", lineHeight: "1.6", color: "var(--color-text-primary)" }}>
              {risk.description}
            </p>

            {risk.original_clause && (
              <div style={{ marginBottom: "10px" }}>
                <p style={{ fontSize: "11px", fontWeight: "500", color: "var(--color-text-secondary)", marginBottom: "4px", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                  Problematic clause
                </p>
                <div style={{
                  background: "#fff5f5", border: "1px solid #fca5a5", borderRadius: "6px",
                  padding: "10px 12px", fontSize: "12px", lineHeight: "1.6",
                  fontFamily: "var(--font-mono, monospace)", color: "#7f1d1d"
                }}>
                  {risk.original_clause}
                </div>
              </div>
            )}

            {risk.suggested_fix && (
              <div style={{ marginBottom: "10px" }}>
                <p style={{ fontSize: "11px", fontWeight: "500", color: "var(--color-text-secondary)", marginBottom: "4px", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                  Suggested replacement
                </p>
                <div style={{
                  background: "#f0fdf4", border: "1px solid #86efac", borderRadius: "6px",
                  padding: "10px 12px", fontSize: "12px", lineHeight: "1.6",
                  fontFamily: "var(--font-mono, monospace)", color: "#14532d"
                }}>
                  {risk.suggested_fix}
                </div>
              </div>
            )}

            {risk.law_reference && (
              <p style={{ fontSize: "11px", color: "var(--color-text-secondary)", margin: 0 }}>
                📋 <span style={{ fontStyle: "italic" }}>{risk.law_reference}</span>
              </p>
            )}
          </div>
        )}
      </div>
    )
  }

  // ── Missing clause card ────────────────────────────────────────────────
  const MissingCard = ({ item, idx }) => {
    const isOpen = expandedMissing === idx
    return (
      <div style={{
        border: "1px solid var(--color-border-secondary)",
        borderLeft: "4px solid #818cf8",
        borderRadius: "10px",
        marginBottom: "10px",
        background: isOpen ? "#f5f3ff" : "var(--color-background-primary)",
        transition: "background 0.2s"
      }}>
        <div
          onClick={() => setExpandedMissing(isOpen ? null : idx)}
          style={{ display: "flex", alignItems: "center", gap: "10px", padding: "12px 14px", cursor: "pointer" }}
        >
          <span style={{ fontSize: "18px" }}>⚠️</span>
          <span style={{ flex: 1, fontSize: "13px", fontWeight: "500", color: "var(--color-text-primary)" }}>
            {item.title}
          </span>
          <span style={{ fontSize: "16px", color: "var(--color-text-secondary)", transform: isOpen ? "rotate(180deg)" : "rotate(0)", transition: "transform 0.2s" }}>▾</span>
        </div>
        {isOpen && (
          <div style={{ padding: "0 14px 14px", borderTop: "1px solid #c7d2fe" }}>
            <p style={{ margin: "10px 0 10px", fontSize: "13px", lineHeight: "1.6", color: "var(--color-text-primary)" }}>
              {item.why_needed}
            </p>
            <p style={{ fontSize: "11px", fontWeight: "500", color: "var(--color-text-secondary)", marginBottom: "4px", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Suggested clause to add
            </p>
            <div style={{
              background: "#f5f3ff", border: "1px solid #c7d2fe", borderRadius: "6px",
              padding: "10px 12px", fontSize: "12px", lineHeight: "1.7",
              fontFamily: "var(--font-mono, monospace)", color: "#3730a3"
            }}>
              {item.suggested_text}
            </div>
            {item.law_reference && (
              <p style={{ fontSize: "11px", color: "var(--color-text-secondary)", margin: "8px 0 0" }}>
                📋 <span style={{ fontStyle: "italic" }}>{item.law_reference}</span>
              </p>
            )}
          </div>
        )}
      </div>
    )
  }

  // ── File handling ──────────────────────────────────────────────────────
  const handleDrag = (e) => {
    e.preventDefault(); e.stopPropagation()
    setDragActive(e.type === "dragenter" || e.type === "dragover")
  }
  const handleDrop = (e) => {
    e.preventDefault(); e.stopPropagation()
    setDragActive(false)
    if (e.dataTransfer.files?.[0]) handleFileUpload(e.dataTransfer.files[0])
  }

  const handleFileUpload = (f) => {
    const valid = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"]
    if (!valid.includes(f.type)) { setError("Please upload PDF, DOCX, or TXT files."); setTimeout(() => setError(null), 5000); return }
    if (f.size > MAX_FILE_SIZE) { setError("File too large (max 10MB)."); return }
    setFile(f); setAnalysis(null); setActiveTab("risks"); setExpandedRisk(null); setExpandedMissing(null)
    runAnalysis(f)
  }

  const runAnalysis = async (f) => {
    setIsAnalyzing(true); setError(null)
    try {
      const result = await apiService.analyzeContract(f)
      setAnalysis(result)
    } catch (err) {
      setError("Analysis failed. Please try again.")
    } finally {
      setIsAnalyzing(false)
    }
  }

  // ── Tab config ─────────────────────────────────────────────────────────
  const TABS = [
    { id: "risks",        label: "Risks",         count: analysis?.risks?.length },
    { id: "missing",      label: "Missing Clauses",count: analysis?.missing_clauses?.length },
    { id: "laws",         label: "Applicable Laws",count: analysis?.applicable_laws?.length },
    { id: "actions",      label: "Action Plan",    count: analysis?.recommendations?.length },
  ]

  const sortedRisks = analysis?.risks
    ? [...analysis.risks].sort((a, b) => getSeverityOrder(a.severity) - getSeverityOrder(b.severity))
    : []

  // ── Risk breakdown counts ──────────────────────────────────────────────
  const riskCounts = sortedRisks.reduce((acc, r) => {
    acc[r.severity] = (acc[r.severity] || 0) + 1; return acc
  }, {})

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="page-enter">
      <div className="doc-page">
        <div className="doc-main">

          {/* ── Page header ────────────────────────────────────────────── */}
          <div style={{ marginBottom: "0.75rem" }}>
            <h1 className="page-title-h1">Document Analyzer</h1>
            <p className="page-title-sub">Upload a contract or legal document for a detailed AI-powered risk report</p>
          </div>

          {/* ── Upload card ─────────────────────────────────────────────── */}
          <div className="card">
            <div className="card-header">
              <h3>Upload Document</h3>
              <p>Supports PDF, DOCX, TXT · Maximum 10 MB</p>
            </div>
            <div className="card-body">
              {error && (
                <div className="auth-alert error" style={{ marginBottom: "1rem" }}>{error}</div>
              )}
              <div
                className={`drop-zone${dragActive ? " active" : ""}`}
                onDragEnter={handleDrag} onDragOver={handleDrag}
                onDragLeave={handleDrag} onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <div className="drop-zone-icon"><Ic.Upload /></div>
                {file
                  ? (<><h4>{file.name}</h4><p>{isAnalyzing ? "Analyzing…" : "Click to replace"}</p></>)
                  : (<><h4>Drag and drop your document here</h4><p>or click to browse files</p></>)
                }
                <button className="btn-select-file" onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click() }}>
                  Select File
                </button>
              </div>
              <input
                ref={fileInputRef} type="file" className="hidden"
                onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0])}
                accept=".pdf,.docx,.txt"
              />
            </div>
          </div>

          {/* ── Loading state ───────────────────────────────────────────── */}
          {isAnalyzing && (
            <div className="card">
              <div className="card-body">
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "1.5rem 0", color: "var(--text-muted)" }}>
                  <div className="spin" />
                  <div>
                    <p style={{ margin: 0, fontWeight: 500 }}>Analyzing document with AI…</p>
                    <p style={{ margin: 0, fontSize: "12px", color: "var(--color-text-secondary)" }}>
                      Identifying risks, missing clauses, and applicable Pakistani laws
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── Full report ─────────────────────────────────────────────── */}
          {analysis && !isAnalyzing && (() => {
            const score = analysis.compliance_score ?? 60
            const riskLevel = analysis.overall_risk ?? "medium"
            const riskColors = SEV_COLOR[riskLevel] || SEV_COLOR.medium

            return (
              <>
                {/* ── Summary banner ───────────────────────────────────── */}
                <div className="card" style={{ borderTop: `4px solid ${riskColors.badge}` }}>
                  <div className="card-body">
                    <div style={{ display: "flex", gap: "20px", alignItems: "flex-start", flexWrap: "wrap" }}>

                      {/* Score dial */}
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "4px", minWidth: "140px" }}>
                        <ScoreDial score={score} />
                        <span style={{
                          fontSize: "11px", fontWeight: "500", padding: "3px 10px",
                          borderRadius: "20px", background: riskColors.badge, color: "#fff",
                          textTransform: "uppercase", letterSpacing: "0.5px"
                        }}>
                          {RISK_LABEL[riskLevel]} Risk
                        </span>
                      </div>

                      {/* Summary text + metadata */}
                      <div style={{ flex: 1, minWidth: "200px" }}>
                        <p style={{ margin: "0 0 4px", fontSize: "12px", color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                          {analysis.document_type || "Legal Document"}
                        </p>
                        <p style={{ margin: "0 0 10px", fontSize: "14px", lineHeight: "1.6", color: "var(--color-text-primary)" }}>
                          {analysis.summary}
                        </p>

                        {/* Metadata pills */}
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                          {analysis.jurisdiction && (
                            <span style={{ fontSize: "11px", padding: "2px 8px", borderRadius: "20px", background: "var(--color-background-secondary)", color: "var(--color-text-secondary)", border: "0.5px solid var(--color-border-tertiary)" }}>
                              📍 {analysis.jurisdiction}
                            </span>
                          )}
                          {analysis.key_dates?.slice(0, 2).map((d, i) => (
                            <span key={i} style={{ fontSize: "11px", padding: "2px 8px", borderRadius: "20px", background: "var(--color-background-secondary)", color: "var(--color-text-secondary)", border: "0.5px solid var(--color-border-tertiary)" }}>
                              📅 {d}
                            </span>
                          ))}
                        </div>

                        {/* Parties */}
                        {analysis.parties?.length > 0 && (
                          <div style={{ marginTop: "10px", display: "flex", flexWrap: "wrap", gap: "6px" }}>
                            {analysis.parties.map((p, i) => (
                              <span key={i} style={{ fontSize: "11px", padding: "2px 8px", borderRadius: "20px", background: "#e0e7ff", color: "#3730a3", border: "1px solid #c7d2fe" }}>
                                👤 {p}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Risk breakdown mini-stats */}
                      <div style={{ display: "flex", flexDirection: "column", gap: "6px", minWidth: "100px" }}>
                        {["critical", "high", "medium", "low"].map(sev => {
                          const cnt = riskCounts[sev] || 0
                          if (!cnt) return null
                          const c = SEV_COLOR[sev]
                          return (
                            <div key={sev} style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                              <div style={{ width: "8px", height: "8px", borderRadius: "50%", background: c.badge }} />
                              <span style={{ fontSize: "11px", color: "var(--color-text-secondary)", textTransform: "capitalize" }}>{sev}</span>
                              <span style={{ fontSize: "12px", fontWeight: "500", color: c.text, marginLeft: "auto" }}>{cnt}</span>
                            </div>
                          )
                        })}
                        <div style={{ borderTop: "0.5px solid var(--color-border-tertiary)", paddingTop: "4px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <span style={{ fontSize: "11px", color: "var(--color-text-secondary)" }}>Total</span>
                          <span style={{ fontSize: "12px", fontWeight: "500" }}>{sortedRisks.length}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* ── Tabs ─────────────────────────────────────────────── */}
                <div style={{
                  display: "flex", gap: "2px", padding: "4px",
                  background: "var(--color-background-secondary)",
                  borderRadius: "10px", marginBottom: "2px"
                }}>
                  {TABS.map(tab => (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      style={{
                        flex: 1, padding: "8px 4px", border: "none", borderRadius: "8px",
                        cursor: "pointer", fontSize: "12px", fontWeight: activeTab === tab.id ? "500" : "400",
                        background: activeTab === tab.id ? "var(--color-background-primary)" : "transparent",
                        color: activeTab === tab.id ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                        boxShadow: activeTab === tab.id ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
                        transition: "all 0.15s"
                      }}
                    >
                      {tab.label}
                      {tab.count > 0 && (
                        <span style={{
                          marginLeft: "4px", fontSize: "10px",
                          background: activeTab === tab.id ? riskColors.badge : "var(--color-border-tertiary)",
                          color: activeTab === tab.id ? "#fff" : "var(--color-text-secondary)",
                          borderRadius: "10px", padding: "1px 5px"
                        }}>
                          {tab.count}
                        </span>
                      )}
                    </button>
                  ))}
                </div>

                {/* ── Tab panels ───────────────────────────────────────── */}
                <div className="card">
                  <div className="card-body" style={{ paddingTop: "1rem" }}>

                    {/* RISKS TAB */}
                    {activeTab === "risks" && (
                      <div>
                        {sortedRisks.length === 0
                          ? <p style={{ color: "var(--color-text-secondary)", fontSize: "13px" }}>No specific risks identified.</p>
                          : sortedRisks.map((risk, i) => <RiskCard key={i} risk={risk} idx={i} />)
                        }
                      </div>
                    )}

                    {/* MISSING CLAUSES TAB */}
                    {activeTab === "missing" && (
                      <div>
                        {(!analysis.missing_clauses || analysis.missing_clauses.length === 0)
                          ? <p style={{ color: "var(--color-text-secondary)", fontSize: "13px" }}>No missing clauses identified.</p>
                          : analysis.missing_clauses.map((item, i) => <MissingCard key={i} item={item} idx={i} />)
                        }
                      </div>
                    )}

                    {/* APPLICABLE LAWS TAB */}
                    {activeTab === "laws" && (
                      <div>
                        {(!analysis.applicable_laws || analysis.applicable_laws.length === 0)
                          ? <p style={{ color: "var(--color-text-secondary)", fontSize: "13px" }}>No laws identified.</p>
                          : analysis.applicable_laws.map((law, i) => (
                            <div key={i} style={{
                              border: "1px solid var(--color-border-tertiary)",
                              borderLeft: "4px solid #0ea5e9",
                              borderRadius: "10px", padding: "12px 14px", marginBottom: "10px",
                              background: "var(--color-background-primary)"
                            }}>
                              <div style={{ display: "flex", alignItems: "baseline", gap: "8px", marginBottom: "6px" }}>
                                <span style={{ fontSize: "14px", fontWeight: "500", color: "var(--color-text-primary)" }}>
                                  {law.name}
                                </span>
                                {law.year && (
                                  <span style={{ fontSize: "11px", background: "#e0f2fe", padding: "1px 6px", borderRadius: "10px", color: "#0369a1" }}>
                                    {law.year}
                                  </span>
                                )}
                              </div>
                              <p style={{ margin: "0 0 8px", fontSize: "13px", lineHeight: "1.6", color: "var(--color-text-secondary)" }}>
                                {law.relevance}
                              </p>
                              {law.key_sections?.length > 0 && (
                                <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                                  {law.key_sections.map((s, si) => (
                                    <span key={si} style={{
                                      fontSize: "11px", padding: "2px 8px",
                                      background: "#f0f9ff", border: "1px solid #bae6fd",
                                      borderRadius: "6px", color: "#0369a1"
                                    }}>
                                      {s}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))
                        }
                      </div>
                    )}

                    {/* ACTION PLAN TAB */}
                    {activeTab === "actions" && (
                      <div>
                        {/* Cost/Timeline info */}
                        <div style={{ display: "flex", gap: "12px", marginBottom: "16px", flexWrap: "wrap" }}>
                          {[
                            { label: "Estimated Cost", value: analysis.estimated_cost || "PKR 25,000–100,000", icon: "💰" },
                            { label: "Review Timeline", value: analysis.timeline || "2–4 weeks", icon: "🕐" },
                          ].map((item, i) => (
                            <div key={i} style={{
                              flex: 1, minWidth: "140px",
                              background: "var(--color-background-secondary)",
                              borderRadius: "8px", padding: "12px 14px"
                            }}>
                              <p style={{ margin: "0 0 2px", fontSize: "11px", color: "var(--color-text-secondary)" }}>
                                {item.icon} {item.label}
                              </p>
                              <p style={{ margin: 0, fontSize: "13px", fontWeight: "500", color: "var(--color-text-primary)" }}>
                                {item.value}
                              </p>
                            </div>
                          ))}
                        </div>

                        {/* Ordered recommendations */}
                        <div>
                          {(analysis.recommendations || []).map((rec, i) => (
                            <div key={i} style={{
                              display: "flex", gap: "12px", alignItems: "flex-start",
                              padding: "10px 0",
                              borderBottom: i < analysis.recommendations.length - 1 ? "0.5px solid var(--color-border-tertiary)" : "none"
                            }}>
                              <div style={{
                                width: "22px", height: "22px", borderRadius: "50%",
                                background: i === 0 ? "#ef4444" : i === 1 ? "#f97316" : "#6366f1",
                                color: "#fff", fontSize: "11px", fontWeight: "500",
                                display: "flex", alignItems: "center", justifyContent: "center",
                                flexShrink: 0, marginTop: "1px"
                              }}>
                                {i + 1}
                              </div>
                              <p style={{ margin: 0, fontSize: "13px", lineHeight: "1.6", color: "var(--color-text-primary)" }}>
                                {rec}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* ── Actions ──────────────────────────────────────────── */}
                <div className="analysis-actions">
                  <button className="btn-download"><Ic.Download />Download Report</button>
                  <button className="btn-share"><Ic.Share />Share with Lawyer</button>
                </div>
              </>
            )
          })()}
        </div>

        {/* ── Sidebar ─────────────────────────────────────────────────────── */}
        <div className="doc-sidebar">
          <div className="sidebar-card">
            <div className="sidebar-card-header">Document Types</div>
            <ul className="doc-type-list">
              {["Contracts & Agreements", "FIR & Police Reports", "Legal Notices", "Court Documents", "Property Papers", "Employment Documents"]
                .map(t => <li key={t} className="doc-type-item">{t}</li>)}
            </ul>
          </div>

          {/* What the report includes */}
          <div className="sidebar-card">
            <div className="sidebar-card-header">Report Includes</div>
            <ul className="doc-type-list">
              {[
                "Compliance score (0–100)",
                "Severity-graded risks",
                "Problematic clause detection",
                "Suggested clause rewrites",
                "Missing standard clauses",
                "Draft clauses to add",
                "Applicable Pakistani laws",
                "Specific section references",
                "Prioritised action plan",
                "Cost & timeline estimate"
              ].map(t => <li key={t} className="doc-type-item">{t}</li>)}
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── FIND LAWYERS PAGE ────────────────────────────────────────────────────────
const FindLawyersPage = () => {
  const [lawyers, setLawyers] = useState([])
  const [specializations, setSpecializations] = useState([])
  const [cities, setCities] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState("")
  const [selectedSpecs, setSelectedSpecs] = useState([])
  const [selectedCities, setSelectedCities] = useState([])

  // Fetch lawyers + meta from backend API
  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      setError(null)
      try {
        const [lawyersRes, specsRes, citiesRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/lawyers/?page_size=100`),
          fetch(`${API_BASE_URL}/api/lawyers/meta/specializations`),
          fetch(`${API_BASE_URL}/api/lawyers/meta/cities`),
        ])
        if (!lawyersRes.ok) throw new Error("Failed to load lawyers")
        const lawyersData = await lawyersRes.json()
        const specsData = specsRes.ok ? await specsRes.json() : []
        const citiesData = citiesRes.ok ? await citiesRes.json() : []
        setLawyers(lawyersData.lawyers || [])
        setSpecializations(specsData)
        setCities(citiesData)
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  const toggleSpec = (s) => setSelectedSpecs((prev) => prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s])
  const toggleCity = (c) => setSelectedCities((prev) => prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c])

  const filtered = lawyers.filter((l) => {
    const q = search.toLowerCase()
    const matchSearch = !search || l.name.toLowerCase().includes(q) || l.specialization.toLowerCase().includes(q) || l.location.toLowerCase().includes(q)
    const matchSpec = selectedSpecs.length === 0 || selectedSpecs.some((s) => l.specialization.toLowerCase().includes(s.toLowerCase()))
    const matchCity = selectedCities.length === 0 || selectedCities.includes(l.location)
    return matchSearch && matchSpec && matchCity
  })

  return (
    <div className="page-enter">
      <div className="lawyers-page">
        <div style={{ marginBottom: "1.25rem" }}>
          <h1 className="page-title-h1">Find Qualified Lawyers</h1>
          <p className="page-title-sub">Connect with verified legal professionals across Pakistan</p>
        </div>

        <div className="search-bar-row">
          <div className="search-input-wrap">
            <Ic.Search />
            <input className="search-input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by name, specialization, or location..." />
          </div>
          <button className="btn-filter"><Ic.Filter />Filters</button>
          <button className="btn-filter"><Ic.NearMe />Near Me</button>
        </div>

        <div className="lawyers-layout">
          <div className="lawyers-filters">
            <div className="filter-card">
              <div className="filter-card-title">Specializations</div>
              <div className="filter-list">
                {specializations.map((s) => (
                  <div key={s} className="filter-item" onClick={() => toggleSpec(s)}>
                    <div className={`filter-checkbox${selectedSpecs.includes(s) ? " checked" : ""}`} />
                    <span className="filter-label">{s}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="filter-card">
              <div className="filter-card-title">Location</div>
              <div className="filter-list">
                {cities.map((c) => (
                  <div key={c} className="filter-item" onClick={() => toggleCity(c)}>
                    <div className={`filter-checkbox${selectedCities.includes(c) ? " checked" : ""}`} />
                    <span className="filter-label">{c}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="lawyers-list">
            {loading ? (
              <div className="coming-soon-card">
                <div className="coming-soon-icon"><div className="spin" /></div>
                <h3>Loading lawyers...</h3>
              </div>
            ) : error ? (
              <div className="coming-soon-card">
                <div className="coming-soon-icon"><Ic.AlertTriangle /></div>
                <h3>Could not load lawyers</h3>
                <p>{error} — make sure the backend is running.</p>
              </div>
            ) : filtered.length === 0 ? (
              <div className="coming-soon-card">
                <div className="coming-soon-icon"><Ic.Users /></div>
                <h3>No lawyers found</h3>
                <p>Try adjusting your search filters.</p>
              </div>
            ) : filtered.map((l) => (
              <div key={l.id} className="lawyer-card">
                <div className="lawyer-card-top">
                  <div className="lawyer-info">
                    <div className="lawyer-avatar">{l.emoji}</div>
                    <div>
                      <div className="lawyer-name">{l.name}</div>
                      <div className="lawyer-spec">{l.specialization}</div>
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    {l.rating > 0 ? (
                      <div className="lawyer-rating">
                        <span className="star-icon">★</span>
                        <span>{l.rating}</span>
                        <span style={{ color: "var(--text-faint)", fontWeight: 400 }}>({l.review_count})</span>
                      </div>
                    ) : (
                      <div className="lawyer-rating" style={{ color: "var(--text-muted)", fontWeight: 500 }}>
                        <span style={{ fontSize: "0.75rem" }}>New listing</span>
                      </div>
                    )}
                    {l.free_consultation ? (
                      <div className="lawyer-rate" style={{ color: "var(--primary)", fontWeight: 600 }}>
                        🆓 {l.free_consultation} free consult
                      </div>
                    ) : l.hourly_rate > 0 ? (
                      <div className="lawyer-rate">Rs {l.hourly_rate?.toLocaleString()}/hr</div>
                    ) : (
                      <div className="lawyer-rate" style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
                        Contact for fee
                      </div>
                    )}
                  </div>
                </div>
                <div className="lawyer-stats">
                  <div className="lawyer-stat"><Ic.Clock /><span>{l.experience_years} years</span></div>
                  <div className="lawyer-stat"><Ic.MapPin /><span>{l.location}</span></div>
                  <div className="lawyer-stat"><Ic.Clock /><span>{l.availability}</span></div>
                  <div className="lawyer-stat"><Ic.Globe /><span>{Array.isArray(l.languages) ? l.languages.join(", ") : l.languages}</span></div>
                </div>
                <div className="lawyer-actions">
                  <button className="btn-message" onClick={() => window.open(`mailto:${l.contact_email}`, "_blank")}><Ic.MessageSq />Message</button>
                  <button className="btn-call" onClick={() => l.contact_phone && window.open(`tel:${l.contact_phone}`, "_blank")}><Ic.Phone />Call</button>
                  <button className="btn-view-profile">View Profile</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// LEGAL EDUCATION PAGE — Fixed version
// Paste this into App.js replacing everything from:
//   // ── LEGAL EDUCATION PAGE
// down to (but not including):
//   // ── PROFILE PAGE
// Also change line: case "education": return <LegalEducationPage />
// to:              case "education": return <LegalEducationPage user={user} />
// ============================================================================

const API_EDU = `${API_BASE_URL}/api/education`

const eduFetch = async (path, opts) => {
  const res = await fetchWithTimeout(`${API_EDU}${path}`, opts)
  if (!res.ok) throw new Error(await parseErrorResponse(res))
  return res.json()
}

// ── Shared helpers ────────────────────────────────────────────────────────────

const EduSpinner = () => (
  <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
    <div className="spin" />
  </div>
)

const EduEmpty = ({ emoji, title, sub }) => (
  <div style={{
    display: "flex", flexDirection: "column", alignItems: "center",
    gap: "0.75rem", padding: "3rem 2rem", background: "var(--bg-white)",
    border: "1px solid var(--border)", borderRadius: 12, textAlign: "center",
  }}>
    <span style={{ fontSize: "2.5rem" }}>{emoji}</span>
    <div style={{ fontWeight: 600, color: "var(--text-dark)", fontSize: "1rem" }}>{title}</div>
    {sub && <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)", maxWidth: 340, lineHeight: 1.5 }}>{sub}</div>}
  </div>
)

const EduProgressBar = ({ percent, height = 5 }) => (
  <div style={{ height, background: "var(--bg-page)", borderRadius: 3, overflow: "hidden" }}>
    <div style={{
      height: "100%", width: `${Math.min(percent, 100)}%`,
      background: percent >= 100 ? "#10B981" : "var(--primary)",
      borderRadius: 3, transition: "width 0.5s ease",
    }} />
  </div>
)

const LevelPill = ({ level }) => {
  const map = { Beginner: { bg: "#D1FAE5", color: "#065F46" }, Intermediate: { bg: "#FEF3C7", color: "#92400E" }, Advanced: { bg: "#FEE2E2", color: "#991B1B" } }
  const s = map[level] || { bg: "#E5E7EB", color: "#374151" }
  return (
    <span style={{
      padding: "0.2rem 0.625rem", borderRadius: "9999px", fontSize: "0.7rem",
      fontWeight: 700, background: s.bg, color: s.color, letterSpacing: "0.03em",
    }}>{level}</span>
  )
}

// ── COURSES TAB ────────────────────────────────────────────────────────────────

const CoursesTab = ({ user, setActiveCourse }) => {
  const [courses, setCourses]       = useState([])
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState(null)
  const [search, setSearch]         = useState("")
  const [levelFilter, setLevelFilter] = useState("")

  useEffect(() => {
    setLoading(true)
    eduFetch(`/courses${user?.id ? `?user_id=${encodeURIComponent(user.id)}` : ""}`)
      .then(setCourses)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [user?.id])

  const filtered = courses.filter(c => {
    const q = search.toLowerCase()
    const matchSearch = !search || c.title?.toLowerCase().includes(q) || c.desc?.toLowerCase().includes(q) || c.category?.toLowerCase().includes(q)
    const matchLevel  = !levelFilter || c.level === levelFilter
    return matchSearch && matchLevel
  })

  if (loading) return <EduSpinner />
  if (error) return <EduEmpty emoji="⚠️" title="Could not load courses" sub={`${error}. Make sure the backend is running and you've called /admin/bootstrap.`} />
  if (courses.length === 0) return <EduEmpty emoji="📚" title="No courses generated yet" sub="Call POST /api/education/admin/bootstrap from your terminal to generate AI courses from your law JSON files." />

  return (
    <div>
      {/* Search bar + level filters */}
      <div style={{ display: "flex", gap: "0.625rem", marginBottom: "1.25rem", flexWrap: "wrap", alignItems: "center" }}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="🔍  Search courses..."
          style={{
            flex: 1, minWidth: 180, padding: "0.5625rem 0.875rem",
            border: "1px solid var(--border)", borderRadius: 8,
            fontSize: "0.875rem", outline: "none", fontFamily: "inherit",
            background: "var(--bg-white)",
          }}
        />
        {["", "Beginner", "Intermediate", "Advanced"].map(l => (
          <button
            key={l}
            onClick={() => setLevelFilter(l)}
            style={{
              padding: "0.5rem 0.875rem", borderRadius: 8, fontSize: "0.8125rem",
              fontWeight: 500, border: "1px solid var(--border)", cursor: "pointer",
              background: levelFilter === l ? "var(--primary)" : "var(--bg-white)",
              color: levelFilter === l ? "white" : "var(--text-muted)",
              transition: "all 0.15s",
            }}
          >{l || "All"}</button>
        ))}
        <span style={{ fontSize: "0.8125rem", color: "var(--text-faint)", marginLeft: "auto" }}>
          {filtered.length} course{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      {filtered.length === 0
        ? <EduEmpty emoji="🔍" title="No courses match" sub="Try a different search or filter." />
        : (
          <div className="courses-grid">
            {filtered.map(course => (
              <EduCourseCard key={course.id} course={course} onClick={() => setActiveCourse(course)} />
            ))}
          </div>
        )
      }
    </div>
  )
}

const EduCourseCard = ({ course, onClick }) => {
  const pct      = course.progress_percent || 0
  const lessonCount = course.lessons?.length || 0
  const catColors = {
    "Family Law": "#8B5CF6", "Banking Law": "#3B82F6",
    "Land & Property Law": "#F59E0B", "Police Law": "#EF4444", "Religious Law": "#10B981",
  }
  const catColor = catColors[course.category] || "var(--primary)"

  return (
    <div
      className="course-card"
      onClick={onClick}
      style={{ cursor: "pointer", display: "flex", flexDirection: "column" }}
    >
      {/* Colored header strip instead of grey placeholder */}
      <div style={{
        height: 100, background: `linear-gradient(135deg, ${catColor}CC, ${catColor}88)`,
        display: "flex", flexDirection: "column", justifyContent: "flex-end",
        padding: "0.75rem", position: "relative", flexShrink: 0,
      }}>
        <span style={{ fontSize: "1.75rem", lineHeight: 1 }}>
          {course.category === "Family Law" ? "👨‍👩‍👧" :
           course.category === "Banking Law" ? "🏦" :
           course.category === "Land & Property Law" ? "🏠" :
           course.category === "Police Law" ? "👮" :
           course.category === "Religious Law" ? "☪️" : "📚"}
        </span>
        <div style={{ display: "flex", gap: "0.375rem", marginTop: "0.375rem", flexWrap: "wrap" }}>
          <LevelPill level={course.level} />
          {course.ai_generated && (
            <span style={{
              padding: "0.2rem 0.5rem", borderRadius: "9999px", fontSize: "0.65rem",
              fontWeight: 700, background: "rgba(255,255,255,0.9)", color: catColor,
            }}>✦ AI</span>
          )}
        </div>
      </div>

      {/* Card body */}
      <div style={{ padding: "1rem", display: "flex", flexDirection: "column", flex: 1 }}>
        {/* Category tag */}
        <div style={{ fontSize: "0.7rem", fontWeight: 600, color: catColor, marginBottom: "0.375rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          {course.category}
        </div>

        <h3 style={{ fontSize: "0.9375rem", fontWeight: 700, color: "var(--text-dark)", marginBottom: "0.375rem", lineHeight: 1.35 }}>
          {course.title}
        </h3>

        <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)", lineHeight: 1.55, marginBottom: "0.75rem", flex: 1 }}>
          {course.desc}
        </p>

        {/* Key topics preview */}
        {course.key_topics?.length > 0 && (
          <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
            {course.key_topics.slice(0, 3).map((t, i) => (
              <span key={i} style={{
                padding: "0.15rem 0.5rem", background: "var(--bg-gray)",
                border: "1px solid var(--border)", borderRadius: "9999px",
                fontSize: "0.68rem", color: "var(--text-muted)",
              }}>{t}</span>
            ))}
            {course.key_topics.length > 3 && (
              <span style={{ fontSize: "0.68rem", color: "var(--text-faint)", padding: "0.15rem 0.25rem" }}>
                +{course.key_topics.length - 3} more
              </span>
            )}
          </div>
        )}

        {/* Meta row */}
        <div style={{
          display: "flex", gap: "0.875rem", fontSize: "0.75rem",
          color: "var(--text-faint)", marginBottom: "0.75rem",
        }}>
          <span>📖 {lessonCount} lessons</span>
          <span>⏱ {course.hours}h</span>
          {course.completed && <span style={{ color: "#10B981", fontWeight: 700 }}>✓ Complete</span>}
        </div>

        {/* Progress or CTA */}
        {pct > 0 ? (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", marginBottom: "0.25rem" }}>
              <span style={{ color: "var(--text-muted)" }}>Progress</span>
              <span style={{ fontWeight: 600, color: "var(--primary)" }}>{pct}%</span>
            </div>
            <EduProgressBar percent={pct} />
            <button className="btn-continue-course" style={{ marginTop: "0.75rem", width: "100%", justifyContent: "center" }}>
              {course.completed ? "Review Course" : "Continue Learning"}
            </button>
          </div>
        ) : (
          <button className="btn-start-course" style={{ width: "100%", justifyContent: "center" }}>
            Start Course →
          </button>
        )}
      </div>
    </div>
  )
}

// ── LESSON CONTENT TABS ────────────────────────────────────────────────────────

const LessonContentTabs = ({ lesson }) => {
  const [activeTab, setActiveTab] = useState("content")

  const tabs = [
    { id: "content", label: "Content", hasContent: !!lesson.content },
    { id: "key_points", label: "Key Points", hasContent: lesson.key_points?.length > 0 },
    { id: "real_world_example", label: "Real World Example", hasContent: !!lesson.real_world_example },
    { id: "law_references", label: "Law References", hasContent: lesson.law_references?.length > 0 },
  ].filter(t => t.hasContent)

  if (tabs.length === 0) return null

  return (
    <div style={{ marginBottom: "1rem" }}>
      {/* Tab buttons */}
      <div style={{
        display: "flex", gap: "0.125rem", marginBottom: "0.875rem",
        borderBottom: "1px solid var(--border)",
      }}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: "0.5rem 1rem", border: "none", borderBottom: activeTab === tab.id ? "2px solid var(--primary)" : "2px solid transparent",
              background: "none", fontSize: "0.8125rem", fontWeight: activeTab === tab.id ? 600 : 500,
              color: activeTab === tab.id ? "var(--primary)" : "var(--text-muted)",
              cursor: "pointer", transition: "all 0.15s",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={{ fontSize: "0.875rem", lineHeight: 1.65, color: "var(--text-mid)" }}>
        {activeTab === "content" && lesson.content && (
          <div dangerouslySetInnerHTML={{ __html: lesson.content.replace(/\n/g, "<br>") }} />
        )}
        {activeTab === "key_points" && lesson.key_points?.length > 0 && (
          <ul style={{ paddingLeft: "1.25rem", margin: 0 }}>
            {lesson.key_points.map((point, i) => (
              <li key={i} style={{ marginBottom: "0.5rem" }}>{point}</li>
            ))}
          </ul>
        )}
        {activeTab === "real_world_example" && lesson.real_world_example && (
          <div style={{ background: "var(--bg-gray)", padding: "0.875rem", borderRadius: 8, border: "1px solid var(--border)" }}>
            <div style={{ fontWeight: 600, color: "var(--text-dark)", marginBottom: "0.5rem" }}>Real World Example</div>
            <div dangerouslySetInnerHTML={{ __html: lesson.real_world_example.replace(/\n/g, "<br>") }} />
          </div>
        )}
        {activeTab === "law_references" && lesson.law_references?.length > 0 && (
          <div>
            <div style={{ fontWeight: 600, color: "var(--text-dark)", marginBottom: "0.5rem" }}>Relevant Laws</div>
            <ul style={{ paddingLeft: "1.25rem", margin: 0 }}>
              {lesson.law_references.map((ref, i) => (
                <li key={i} style={{ marginBottom: "0.25rem" }}>{ref}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

// ── COURSE DETAIL MODAL ────────────────────────────────────────────────────────

const CourseDetailModal = ({ course, user, onClose }) => {
  const [openLesson, setOpenLesson] = useState(null)
  const [progress, setProgress]     = useState({
    progress_percent:  course.progress_percent  || 0,
    lessons_completed: course.lessons_completed || 0,
  })
  const [saving, setSaving] = useState(false)
  const [doneIndices, setDoneIndices] = useState([])

  const lessons = course.lessons || []

  const markComplete = async (lesson) => {
    if (!user?.id || doneIndices.includes(lesson.index)) return
    setSaving(true)
    try {
      const res = await eduFetch("/progress", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: user.id, course_id: course.id, lesson_index: lesson.index }),
      })
      setProgress({ progress_percent: res.progress_percent, lessons_completed: res.lessons_completed })
      setDoneIndices(prev => [...prev, lesson.index])
    } catch (e) { console.error("Progress error:", e) }
    finally { setSaving(false) }
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)",
        zIndex: 300, display: "flex", alignItems: "flex-start",
        justifyContent: "center", padding: "1.5rem", overflowY: "auto",
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "var(--bg-white)", borderRadius: 16, width: "100%",
          maxWidth: 740, boxShadow: "0 25px 60px rgba(0,0,0,0.3)",
          marginTop: "1rem", marginBottom: "1rem",
        }}
      >
        {/* Header */}
        <div style={{
          padding: "1.5rem", borderBottom: "1px solid var(--border)",
          display: "flex", justifyContent: "space-between", alignItems: "flex-start",
          position: "sticky", top: 0, background: "var(--bg-white)",
          borderRadius: "16px 16px 0 0", zIndex: 1,
        }}>
          <div style={{ flex: 1, marginRight: "1rem" }}>
            <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
              <LevelPill level={course.level} />
              <span style={{ fontSize: "0.75rem", color: "var(--text-faint)" }}>{course.category}</span>
              {course.ai_generated && <span style={{ fontSize: "0.7rem", color: "var(--primary)", fontWeight: 700 }}>✦ AI Generated</span>}
            </div>
            <h2 style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--text-dark)", margin: 0, lineHeight: 1.35 }}>
              {course.title}
            </h2>
          </div>
          <button
            onClick={onClose}
            style={{
              width: 32, height: 32, borderRadius: "50%", border: "1px solid var(--border)",
              background: "var(--bg-gray)", color: "var(--text-muted)", fontSize: "1rem",
              cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
              flexShrink: 0,
            }}
          >✕</button>
        </div>

        <div style={{ padding: "1.5rem" }}>
          {/* Progress */}
          {user && (
            <div style={{
              padding: "0.875rem 1rem", background: "var(--primary-faint)",
              border: "1px solid var(--primary-light)", borderRadius: 10, marginBottom: "1.25rem",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.375rem", fontSize: "0.8125rem" }}>
                <span style={{ color: "var(--text-mid)", fontWeight: 500 }}>Your Progress</span>
                <span style={{ fontWeight: 700, color: "var(--primary)" }}>{progress.progress_percent}%</span>
              </div>
              <EduProgressBar percent={progress.progress_percent} height={8} />
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.375rem" }}>
                {progress.lessons_completed} of {lessons.length} lessons completed
              </div>
            </div>
          )}

          {/* Overview */}
          {course.overview && (
            <div style={{
              padding: "1rem", background: "var(--bg-gray)", borderRadius: 10,
              marginBottom: "1.25rem", fontSize: "0.875rem", color: "var(--text-mid)", lineHeight: 1.65,
              borderLeft: "3px solid var(--primary)",
            }}>
              {course.overview}
            </div>
          )}

          {/* Key topics */}
          {course.key_topics?.length > 0 && (
            <div style={{ marginBottom: "1.25rem" }}>
              <div style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-dark)", marginBottom: "0.5rem" }}>
                Key Topics
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
                {course.key_topics.map((t, i) => (
                  <span key={i} style={{
                    padding: "0.25rem 0.75rem", background: "var(--primary-faint)",
                    border: "1px solid var(--primary-light)", borderRadius: "9999px",
                    fontSize: "0.8125rem", color: "var(--primary)", fontWeight: 500,
                  }}>{t}</span>
                ))}
              </div>
            </div>
          )}

          {/* Learning outcomes */}
          {course.learning_outcomes?.length > 0 && (
            <div style={{ marginBottom: "1.25rem" }}>
              <div style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-dark)", marginBottom: "0.5rem" }}>
                What You'll Learn
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
                {course.learning_outcomes.map((o, i) => (
                  <div key={i} style={{ display: "flex", gap: "0.5rem", fontSize: "0.875rem", color: "var(--text-mid)" }}>
                    <span style={{ color: "var(--primary)", fontWeight: 700, flexShrink: 0 }}>✓</span>
                    <span>{o}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Lessons */}
          <div style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-dark)", marginBottom: "0.75rem" }}>
            Lessons ({lessons.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {lessons.map((lesson, idx) => {
              const isDone = doneIndices.includes(lesson.index !== undefined ? lesson.index : idx) || idx < (course.lessons_completed || 0)
              const isOpen = openLesson === idx
              return (
                <div key={idx} style={{
                  border: `1px solid ${isDone ? "var(--primary-light)" : "var(--border)"}`,
                  borderRadius: 10,
                  background: isDone ? "var(--primary-faint)" : "var(--bg-white)",
                  overflow: "hidden",
                }}>
                  {/* Lesson header */}
                  <div
                    onClick={() => setOpenLesson(isOpen ? null : idx)}
                    style={{
                      display: "flex", alignItems: "center", gap: "0.875rem",
                      padding: "0.75rem 1rem", cursor: "pointer",
                    }}
                  >
                    <div style={{
                      width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
                      background: isDone ? "var(--primary)" : "var(--bg-gray)",
                      border: `2px solid ${isDone ? "var(--primary)" : "var(--border)"}`,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: isDone ? "0.75rem" : "0.7rem",
                      fontWeight: 700,
                      color: isDone ? "white" : "var(--text-faint)",
                    }}>
                      {isDone ? "✓" : idx + 1}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-dark)" }}>
                        {lesson.title}
                      </div>
                      {lesson.law_references?.[0] && (
                        <div style={{ fontSize: "0.75rem", color: "var(--text-faint)", marginTop: "0.125rem" }}>
                          {lesson.law_references[0]}
                        </div>
                      )}
                    </div>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-faint)", flexShrink: 0 }}>
                      {isOpen ? "▲" : "▼"}
                    </span>
                  </div>

                  {/* Expanded lesson content */}
                  {isOpen && (
                    <div style={{ padding: "0.875rem 1rem 1rem", borderTop: "1px solid var(--border)" }}>
                      {(lesson.content || lesson.key_points?.length > 0 || lesson.real_world_example || lesson.law_references?.length > 0)
                        ? <LessonContentTabs lesson={lesson} />
                        : (
                          <p style={{ fontSize: "0.875rem", color: "var(--text-mid)", lineHeight: 1.65, margin: "0 0 0.875rem" }}>
                            {lesson.summary || "This lesson covers key concepts from the relevant Pakistani legislation."}
                          </p>
                        )}

                      {user && !isDone && (
                        <button
                          onClick={() => markComplete(lesson.index !== undefined ? lesson : { ...lesson, index: idx })}
                          disabled={saving}
                          style={{
                            padding: "0.5rem 1.125rem", background: "var(--primary)",
                            color: "white", border: "none", borderRadius: 8,
                            fontSize: "0.8125rem", fontWeight: 700, cursor: saving ? "wait" : "pointer",
                            opacity: saving ? 0.7 : 1,
                          }}
                        >
                          {saving ? "Saving..." : "✓ Mark as Complete"}
                        </button>
                      )}
                      {isDone && (
                        <span style={{ fontSize: "0.8125rem", color: "var(--primary)", fontWeight: 600 }}>
                          ✓ Completed
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* Difficulty note */}
          {course.difficulty_notes && (
            <div style={{
              marginTop: "1.25rem", padding: "0.75rem 1rem",
              background: "var(--bg-gray)", borderRadius: 8,
              fontSize: "0.8125rem", color: "var(--text-muted)",
            }}>
              💡 {course.difficulty_notes}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── LAW LIBRARY TAB ────────────────────────────────────────────────────────────

const LawLibraryTab = () => {
  const [entries, setEntries]     = useState([])
  const [stats, setStats]         = useState(null)
  const [categories, setCategories] = useState([])
  const [loading, setLoading]     = useState(true)
  const [search, setSearch]       = useState("")
  const [category, setCategory]   = useState("")

  useEffect(() => {
    Promise.all([
      eduFetch("/library"),
      eduFetch("/library/categories"),
      eduFetch("/library/stats"),
    ]).then(([lib, cats, st]) => {
      setEntries(lib); setCategories(cats); setStats(st)
    }).catch(console.error).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const params = new URLSearchParams()
    if (search) params.set("search", search)
    if (category) params.set("category", category)
    eduFetch(`/library?${params}`).then(setEntries).catch(console.error)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, category])

  if (loading && !entries.length) return <EduSpinner />

  return (
    <div>
      {/* Stats */}
      {stats && (
        <div style={{ display: "flex", gap: "0.875rem", marginBottom: "1.25rem", flexWrap: "wrap" }}>
          {[["⚖️", stats.total_laws, "Laws"], ["📄", stats.total_sections, "Sections"], ["📂", Object.keys(stats.by_category || {}).length, "Categories"]].map(([emoji, val, label]) => (
            <div key={label} style={{
              flex: 1, minWidth: 110, padding: "0.875rem",
              background: "var(--bg-white)", border: "1px solid var(--border)",
              borderRadius: 10, display: "flex", alignItems: "center", gap: "0.625rem",
            }}>
              <span style={{ fontSize: "1.25rem" }}>{emoji}</span>
              <div>
                <div style={{ fontWeight: 800, fontSize: "1.125rem", color: "var(--primary)" }}>{(val || 0).toLocaleString()}</div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{label}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Search + filter */}
      <div style={{ display: "flex", gap: "0.625rem", marginBottom: "1.25rem", flexWrap: "wrap" }}>
        <input
          value={search} onChange={e => setSearch(e.target.value)}
          placeholder="🔍  Search laws by name or keyword..."
          style={{
            flex: 1, minWidth: 200, padding: "0.5625rem 0.875rem",
            border: "1px solid var(--border)", borderRadius: 8,
            fontSize: "0.875rem", outline: "none", fontFamily: "inherit",
            background: "var(--bg-white)",
          }}
        />
        <select
          value={category} onChange={e => setCategory(e.target.value)}
          style={{
            padding: "0.5625rem 0.875rem", border: "1px solid var(--border)",
            borderRadius: 8, fontSize: "0.875rem", outline: "none",
            fontFamily: "inherit", background: "var(--bg-white)", color: "var(--text-mid)",
          }}
        >
          <option value="">All Categories</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      {loading ? <EduSpinner /> : entries.length === 0 ? (
        <EduEmpty emoji="📚" title="No laws found" sub="Try a different search term or category." />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {entries.map(entry => (
            <div key={entry.id} style={{
              background: "var(--bg-white)", border: "1px solid var(--border)",
              borderRadius: 10, padding: "0.875rem 1.125rem",
              display: "flex", alignItems: "center", gap: "1rem",
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap", marginBottom: "0.25rem" }}>
                  <span style={{ fontWeight: 600, fontSize: "0.9rem", color: "var(--text-dark)" }}>{entry.title}</span>
                  <span style={{
                    padding: "0.1rem 0.5rem", background: "var(--primary-faint)",
                    color: "var(--primary)", borderRadius: "9999px",
                    fontSize: "0.68rem", fontWeight: 600, flexShrink: 0,
                  }}>{entry.category}</span>
                  {entry.year > 0 && (
                    <span style={{ fontSize: "0.75rem", color: "var(--text-faint)", flexShrink: 0 }}>{entry.year}</span>
                  )}
                </div>
                <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                  {entry.section_count} section{entry.section_count !== 1 ? "s" : ""}
                  {entry.tags?.length > 0 && (
                    <span style={{ color: "var(--text-faint)" }}>
                      {" · "}{entry.tags.slice(0, 4).join(", ")}
                    </span>
                  )}
                </div>
              </div>
              <a
                href={entry.download_url} target="_blank" rel="noopener noreferrer"
                onClick={e => e.stopPropagation()}
                style={{
                  padding: "0.4375rem 0.875rem", border: "1.5px solid var(--primary)",
                  borderRadius: 8, fontSize: "0.8125rem", fontWeight: 600,
                  color: "var(--primary)", textDecoration: "none",
                  whiteSpace: "nowrap", flexShrink: 0,
                }}
              >View ↗</a>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── ASSESSMENTS TAB ────────────────────────────────────────────────────────────

const AssessmentsTab = () => {
  const [list, setList]         = useState([])
  const [loading, setLoading]   = useState(true)
  const [active, setActive]     = useState(null)
  const [questions, setQuestions] = useState([])
  const [answers, setAnswers]   = useState({})
  const [result, setResult]     = useState(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    eduFetch("/assessments").then(setList).catch(console.error).finally(() => setLoading(false))
  }, [])

  const startQuiz = async (a) => {
    setResult(null); setAnswers({})
    try {
      const data = await eduFetch(`/assessments/${a.id}`)
      setQuestions(data.questions || [])
      setActive(data)
    } catch (e) { console.error(e) }
  }

  const submitQuiz = async () => {
    const unanswered = questions.filter(q => answers[q.id] === undefined)
    if (unanswered.length > 0) { alert(`Please answer all ${unanswered.length} remaining questions.`); return }
    setSubmitting(true)
    try {
      const res = await eduFetch(`/assessments/${active.id}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answers }),
      })
      setResult(res)
    } catch (e) { console.error(e) }
    finally { setSubmitting(false) }
  }

  if (loading) return <EduSpinner />

  // ── Active quiz ──
  if (active && !result) {
    const answered = Object.keys(answers).length
    return (
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.25rem" }}>
          <button
            onClick={() => { setActive(null); setQuestions([]) }}
            style={{
              padding: "0.375rem 0.875rem", border: "1px solid var(--border)",
              borderRadius: 8, fontSize: "0.8125rem", color: "var(--text-muted)",
              cursor: "pointer", background: "var(--bg-white)",
            }}
          >← Back</button>
          <div>
            <div style={{ fontWeight: 700, color: "var(--text-dark)", fontSize: "0.9375rem" }}>{active.title}</div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              {questions.length} questions · Pass: {active.pass_mark}%
            </div>
          </div>
          <div style={{ marginLeft: "auto", fontSize: "0.8125rem", color: "var(--primary)", fontWeight: 600 }}>
            {answered}/{questions.length} answered
          </div>
        </div>

        <EduProgressBar percent={Math.round((answered / questions.length) * 100)} height={6} />
        <div style={{ marginBottom: "1.25rem" }} />

        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {questions.map((q, qi) => (
            <div key={q.id} style={{
              background: "var(--bg-white)", border: `1px solid ${answers[q.id] !== undefined ? "var(--primary-light)" : "var(--border)"}`,
              borderRadius: 12, padding: "1.25rem",
            }}>
              <div style={{ fontWeight: 600, fontSize: "0.9375rem", color: "var(--text-dark)", marginBottom: "0.875rem", lineHeight: 1.45 }}>
                <span style={{ color: "var(--primary)", marginRight: "0.5rem" }}>Q{qi + 1}.</span>
                {q.text}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {q.options.map((opt, oi) => {
                  const selected = answers[q.id] === oi
                  return (
                    <div
                      key={oi}
                      onClick={() => setAnswers(prev => ({ ...prev, [q.id]: oi }))}
                      style={{
                        padding: "0.625rem 0.875rem", borderRadius: 8, cursor: "pointer",
                        border: `1.5px solid ${selected ? "var(--primary)" : "var(--border)"}`,
                        background: selected ? "var(--primary-faint)" : "var(--bg-gray)",
                        color: selected ? "var(--primary)" : "var(--text-mid)",
                        fontWeight: selected ? 600 : 400, fontSize: "0.875rem",
                        display: "flex", gap: "0.625rem", alignItems: "center",
                        transition: "all 0.12s",
                      }}
                    >
                      <span style={{
                        width: 18, height: 18, borderRadius: "50%", flexShrink: 0,
                        border: `2px solid ${selected ? "var(--primary)" : "var(--border-dark)"}`,
                        background: selected ? "var(--primary)" : "transparent",
                        display: "flex", alignItems: "center", justifyContent: "center",
                      }}>
                        {selected && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "white", display: "block" }} />}
                      </span>
                      {opt}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: "1.5rem", display: "flex", justifyContent: "flex-end" }}>
          <button
            onClick={submitQuiz}
            disabled={submitting || answered < questions.length}
            style={{
              padding: "0.6875rem 2rem", background: "var(--primary)", color: "white",
              border: "none", borderRadius: 8, fontSize: "0.9375rem", fontWeight: 700,
              cursor: answered < questions.length ? "not-allowed" : "pointer",
              opacity: answered < questions.length ? 0.5 : 1,
            }}
          >{submitting ? "Submitting..." : "Submit →"}</button>
        </div>
      </div>
    )
  }

  // ── Results ──
  if (result) {
    const passed = result.passed
    return (
      <div>
        <div style={{
          background: passed ? "var(--primary-faint)" : "#FEF2F2",
          border: `2px solid ${passed ? "var(--primary-light)" : "#FECACA"}`,
          borderRadius: 16, padding: "2rem", textAlign: "center", marginBottom: "1.5rem",
        }}>
          <div style={{ fontSize: "3rem", marginBottom: "0.5rem" }}>{passed ? "🎉" : "📖"}</div>
          <div style={{ fontSize: "2.75rem", fontWeight: 800, color: passed ? "var(--primary)" : "#EF4444", lineHeight: 1 }}>
            {result.percentage}%
          </div>
          <div style={{ fontWeight: 700, fontSize: "1.0625rem", color: "var(--text-dark)", marginTop: "0.5rem" }}>
            {passed ? "Passed!" : "Not passed — keep studying"}
          </div>
          <div style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginTop: "0.25rem" }}>
            {result.score}/{result.total} correct · Pass mark: {result.pass_mark}%
          </div>
        </div>

        <div style={{ fontWeight: 700, color: "var(--text-dark)", marginBottom: "0.75rem" }}>Question Review</div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginBottom: "1.5rem" }}>
          {result.results.map((r, i) => {
            const q = questions.find(q => q.id === r.question_id)
            return (
              <div key={r.question_id} style={{
                background: "var(--bg-white)",
                border: `1px solid ${r.correct ? "#D1FAE5" : "#FECACA"}`,
                borderLeft: `4px solid ${r.correct ? "#10B981" : "#EF4444"}`,
                borderRadius: 10, padding: "1rem",
              }}>
                <div style={{ fontWeight: 600, fontSize: "0.875rem", color: "var(--text-dark)", marginBottom: "0.5rem" }}>
                  {r.correct ? "✅" : "❌"} Q{i + 1}: {q?.text}
                </div>
                {!r.correct && r.chosen >= 0 && (
                  <div style={{ fontSize: "0.8125rem", color: "#EF4444", marginBottom: "0.25rem" }}>
                    Your answer: {q?.options[r.chosen]}
                  </div>
                )}
                <div style={{ fontSize: "0.8125rem", color: "#10B981", fontWeight: 500 }}>
                  Correct: {q?.options[r.correct_answer]}
                </div>
                {r.explanation && (
                  <div style={{
                    marginTop: "0.5rem", padding: "0.5rem 0.75rem",
                    background: "var(--bg-gray)", borderRadius: 6,
                    fontSize: "0.8125rem", color: "var(--text-muted)", lineHeight: 1.55,
                  }}>
                    💡 {r.explanation}
                    {r.law_reference && <span style={{ color: "var(--primary)", fontWeight: 600 }}> · {r.law_reference}</span>}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button
            onClick={() => { setResult(null); setAnswers({}); setActive(null) }}
            style={{
              padding: "0.625rem 1.25rem", border: "1px solid var(--border)",
              borderRadius: 8, fontSize: "0.875rem", fontWeight: 600,
              color: "var(--text-mid)", cursor: "pointer", background: "none",
            }}
          >← Assessments</button>
          <button
            onClick={() => { setResult(null); setAnswers({}) }}
            style={{
              padding: "0.625rem 1.25rem", background: "var(--primary)", color: "white",
              border: "none", borderRadius: 8, fontSize: "0.875rem", fontWeight: 600,
              cursor: "pointer",
            }}
          >Retry</button>
        </div>
      </div>
    )
  }

  // ── Assessment list ──
  if (list.length === 0) return (
    <EduEmpty emoji="📝" title="No assessments yet"
      sub="Run POST /api/education/admin/bootstrap in your terminal to generate AI assessments from your law files." />
  )

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
      {list.map(a => (
        <div key={a.id} style={{
          background: "var(--bg-white)", border: "1px solid var(--border)",
          borderRadius: 12, padding: "1.125rem 1.25rem",
          display: "flex", alignItems: "center", gap: "1rem",
        }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: "0.9375rem", color: "var(--text-dark)", marginBottom: "0.25rem" }}>
              {a.title}
              {a.ai_generated && <span style={{ marginLeft: "0.5rem", fontSize: "0.7rem", color: "var(--primary)", fontWeight: 700 }}>✦ AI</span>}
            </div>
            <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "0.375rem" }}>{a.description}</div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-faint)" }}>
              📝 {a.question_count} questions · ✓ Pass: {a.pass_mark}%
            </div>
          </div>
          <button
            onClick={() => startQuiz(a)}
            style={{
              padding: "0.5625rem 1.25rem", background: "var(--primary)", color: "white",
              border: "none", borderRadius: 8, fontSize: "0.875rem", fontWeight: 700,
              cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0,
            }}
          >Start →</button>
        </div>
      ))}
    </div>
  )
}

// ── MY PROGRESS TAB ────────────────────────────────────────────────────────────

const MyProgressTab = ({ user }) => {
  const [progress, setProgress] = useState({})
  const [loading, setLoading]   = useState(true)

  useEffect(() => {
    if (!user?.id) { setLoading(false); return }
    eduFetch(`/progress/${user.id}`).then(setProgress).catch(console.error).finally(() => setLoading(false))
  }, [user?.id])

  if (!user) return <EduEmpty emoji="🔐" title="Sign in to track progress" sub="Your course progress will appear here once you're logged in." />
  if (loading) return <EduSpinner />

  const entries = Object.entries(progress)
  if (entries.length === 0) return <EduEmpty emoji="📊" title="No progress yet" sub="Open a course and complete lessons to see your progress here." />

  const completed = entries.filter(([, p]) => p.completed).length

  return (
    <div>
      <div style={{ display: "flex", gap: "0.875rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
        {[["📚", entries.length, "Started"], ["✅", completed, "Completed"], ["🎯", entries.length - completed, "In Progress"]].map(([emoji, val, label]) => (
          <div key={label} style={{
            flex: 1, minWidth: 100, padding: "1rem", background: "var(--bg-white)",
            border: "1px solid var(--border)", borderRadius: 10, textAlign: "center",
          }}>
            <div style={{ fontSize: "1.5rem" }}>{emoji}</div>
            <div style={{ fontWeight: 800, fontSize: "1.5rem", color: "var(--primary)" }}>{val}</div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{label}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {entries.map(([courseId, p]) => (
          <div key={courseId} style={{
            background: "var(--bg-white)", border: "1px solid var(--border)",
            borderRadius: 12, padding: "1.125rem",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.625rem" }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: "0.9375rem", color: "var(--text-dark)" }}>{p.course_title}</div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>
                  {p.lessons_completed}/{p.total_lessons} lessons · {new Date(p.updated_at).toLocaleDateString()}
                </div>
              </div>
              <span style={{
                padding: "0.25rem 0.75rem", borderRadius: "9999px", fontSize: "0.8125rem", fontWeight: 700,
                background: p.completed ? "var(--primary-faint)" : "var(--bg-gray)",
                color: p.completed ? "var(--primary)" : "var(--text-muted)",
              }}>{p.completed ? "✓ Done" : `${p.progress_percent}%`}</span>
            </div>
            <EduProgressBar percent={p.progress_percent} height={6} />
          </div>
        ))}
      </div>
    </div>
  )
}

// ── MAIN PAGE ──────────────────────────────────────────────────────────────────

const LegalEducationPage = ({ user }) => {
  const [activeTab, setActivePage2]   = useState("courses")
  const [activeCourse, setActiveCourse] = useState(null)

  const TABS = [
    { key: "courses",     label: "Courses",     emoji: "📚" },
    { key: "library",     label: "Law Library", emoji: "⚖️" },
    { key: "assessments", label: "Assessments", emoji: "📝" },
    { key: "progress",    label: "My Progress", emoji: "📊" },
  ]

  return (
    <div className="page-enter">
      <div className="education-page">
        <div style={{ marginBottom: "1.25rem" }}>
          <h1 className="page-title-h1">Legal Education Portal</h1>
          <p className="page-title-sub">AI-powered courses from actual Pakistani law · 5 law categories</p>
        </div>

        <div className="edu-tabs">
          {TABS.map(t => (
            <button
              key={t.key}
              className={`edu-tab-btn${activeTab === t.key ? " active" : ""}`}
              onClick={() => setActivePage2(t.key)}
            >
              {t.emoji} {t.label}
            </button>
          ))}
        </div>

        {activeTab === "courses"     && <CoursesTab user={user} setActiveCourse={setActiveCourse} />}
        {activeTab === "library"     && <LawLibraryTab />}
        {activeTab === "assessments" && <AssessmentsTab />}
        {activeTab === "progress"    && <MyProgressTab user={user} />}

        {activeCourse && (
          <CourseDetailModal course={activeCourse} user={user} onClose={() => setActiveCourse(null)} />
        )}
      </div>
    </div>
  )
}

// ── PROFILE PAGE ─────────────────────────────────────────────────────────────
const ProfilePage = ({ user, onLogout }) => (
  <div className="page-enter">
    <div className="profile-page">
      <h1 className="page-title-h1" style={{ marginBottom: "1.25rem" }}>My Profile</h1>
      <div className="profile-card">
        <div className="profile-avatar-large">{user?.name?.[0]?.toUpperCase() || "U"}</div>
        <div>
          <div className="profile-name">{user?.name || "User"}</div>
          <div className="profile-email">{user?.email || ""}</div>
        </div>
      </div>
      <div className="profile-stats-row">
        {[["12","Chat Sessions"],["4","Documents Analyzed"],["2","Courses Enrolled"]].map(([v, l]) => (
          <div key={l} className="profile-stat-card">
            <div className="profile-stat-value">{v}</div>
            <div className="profile-stat-label">{l}</div>
          </div>
        ))}
      </div>
      <button className="btn-logout" onClick={onLogout}><Ic.LogOut />Sign Out</button>
    </div>
  </div>
)

// ── MAIN APP ─────────────────────────────────────────────────────────────────
const App = () => {
  const [activePage, setActivePage] = useState("home")
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [user, setUser] = useState(null)
  const [isCheckingAuth, setIsCheckingAuth] = useState(true)

  useEffect(() => {
    const check = async () => {
      try {
        const session = await apiService.checkSession()
        if (session.authenticated && session.user) { setUser(session.user); setIsAuthenticated(true) }
      } catch { authHelper.logout() }
      setIsCheckingAuth(false)
    }
    check()
  }, [])

  const handleLoginSuccess = (userData) => { setUser(userData); setIsAuthenticated(true) }

  const handleLogout = async () => {
    try { await apiService.logout() } catch {}
    setUser(null); setIsAuthenticated(false); setActivePage("home")
  }

  if (isCheckingAuth) {
    return (
      <div className="app-loading">
        <div className="spin" />
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Loading LegalEase...</p>
      </div>
    )
  }

  if (!isAuthenticated) return <AuthPage onLoginSuccess={handleLoginSuccess} />

  const renderPage = () => {
    switch (activePage) {
      case "home":      return <HomePage setActivePage={setActivePage} />
      case "chat":      return <ChatPage setActivePage={setActivePage} />
      case "document":  return <DocumentPage />
      case "lawyers":   return <FindLawyersPage />
      case "education": return <LegalEducationPage user={user} />
      case "profile":   return <ProfilePage user={user} onLogout={handleLogout} />
      default:          return <HomePage setActivePage={setActivePage} />
    }
  }

  return (
    <div className="app">
      <TopNav activePage={activePage} setActivePage={setActivePage} user={user} onLogout={handleLogout} />
      <div className="page-wrapper">{renderPage()}</div>
    </div>
  )
}

export default App