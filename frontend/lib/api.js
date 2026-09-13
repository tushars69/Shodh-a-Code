const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000';
const AI_URL = process.env.NEXT_PUBLIC_AI_URL || 'http://localhost:8000';

function authHeaders() {
  if (typeof window === 'undefined') return {};
  const token = window.localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function joinContest(contestId, username) {
  const res = await fetch(`${API_URL}/auth/join-contest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contestId, username }),
  });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  window.localStorage.setItem('token', data.token);
  window.localStorage.setItem('user', JSON.stringify(data.user));
  return data;
}

export async function getContest(contestId) {
  const res = await fetch(`${API_URL}/contests/${contestId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listProblems(contestId) {
  const res = await fetch(`${API_URL}/contests/${contestId}/problems`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function submitCode(contestId, problemId, language, sourceCode) {
  const clientSubmissionKey = `${problemId}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const res = await fetch(`${API_URL}/submissions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ contestId, problemId, language, sourceCode, clientSubmissionKey }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSubmission(id) {
  const res = await fetch(`${API_URL}/submissions/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getLeaderboard(contestId) {
  const res = await fetch(`${API_URL}/contests/${contestId}/leaderboard`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function askAi(question, user, orgId) {
  const res = await fetch(`${AI_URL}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      requester_role: user.role,
      requester_user_id: user.id,
      org_id: orgId,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function currentUser() {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem('user');
  return raw ? JSON.parse(raw) : null;
}
