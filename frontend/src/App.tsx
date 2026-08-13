import React, { useState, useEffect } from 'react';
import './App.css';

interface Plan {
  id: string;
  name: string;
  price_cents: number;
}

interface Payment {
  id: string;
  plan_change_id: string;
  merchant_reference: string;
  gateway_charge_id: string | null;
  amount_cents: number;
  status: string;
  created_at: string;
}

interface PlanChange {
  id: string;
  subscription_id: string;
  from_plan_id: string | null;
  from_plan_name: string;
  to_plan_id: string | null;
  to_plan_name: string;
  credit_cents: number;
  charge_cents: number;
  net_cents: number;
  status: string;
  requested_at: string;
  effective_at: string;
  idempotency_key: string;
}

interface Subscription {
  id: string;
  customer_id: string;
  customer_name: string;
  plan_id: string | null;
  plan_name: string;
  plan_price_cents: number;
  status: string;
  cycle_start: string;
  cycle_end: string;
  version: number;
  pending_plan_change: PlanChange | null;
  plan_changes: PlanChange[];
  payments: Payment[];
}

interface LedgerEntry {
  id: string;
  customer_name?: string;
  type: string;
  amount_cents: number;
  status: string;
  is_reconciliation: boolean;
  created_at: string;
  posted_at: string | null;
}

interface ReconciliationRecord {
  id: string;
  payment_id: string;
  plan_change_id: string;
  ledger_entry_id: string;
  reason: string;
  status: string;
  created_at: string;
  resolved_at: string | null;
  resolution_notes: string | null;
  amount_cents: number;
  merchant_reference: string;
}

interface LoginAuditRecord {
  id: string;
  email_attempted: string;
  login_at: string;
  success: boolean;
  ip_address: string | null;
  user_agent: string | null;
  failure_reason: string | null;
}

interface CustomerAdminView {
  id: string;
  name: string;
  email: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
  subscription_id: string | null;
  plan_name: string;
  status: string;
}

interface ProrationPreview {
  from_plan_id: string | null;
  from_plan_name: string;
  to_plan_id: string | null;
  to_plan_name: string;
  credit_cents: number;
  charge_cents: number;
  net_cents: number;
  remaining_ratio: number;
  effective_at: string;
}

interface AuthSession {
  token: string;
  role: "CUSTOMER" | "ADMIN";
  email: string;
  name: string;
  customer_id?: string;
  subscription_id?: string;
}

function App() {
  // Environment variables are easy to paste with a trailing slash. Normalize
  // it here so requests never become `//auth/login`, which Vercel redirects
  // and browsers reject during a CORS preflight request.
  const baseUrl = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/+$/, "");

  // Auth State
  const [session, setSession] = useState<AuthSession | null>(() => {
    const saved = localStorage.getItem("prora_session");
    return saved ? JSON.parse(saved) : null;
  });

  // Auth Screen tab state
  const [authTab, setAuthTab] = useState<"login_cust" | "register_cust" | "login_admin">("login_cust");

  // Auth Form parameters
  const [authName, setAuthName] = useState("");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authConfirmPassword, setAuthConfirmPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);

  // Security Page parameters
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [passwordChangeMsg, setPasswordChangeMsg] = useState<{ text: string; success: boolean } | null>(null);

  // Tab State
  const [customerTab, setCustomerTab] = useState<"dashboard" | "ledger" | "security">("dashboard");
  const [adminTab, setAdminTab] = useState<"overview" | "customers" | "reconciliations" | "ledger" | "logins" | "webhooks" | "system">("overview");

  // Customer Data State
  const [plans, setPlans] = useState<Plan[]>([]);
  const [custSub, setCustSub] = useState<Subscription | null>(null);
  const [custLedger, setCustLedger] = useState<LedgerEntry[]>([]);
  const [custTimeline, setCustTimeline] = useState<PlanChange[]>([]);

  // Customer Simulator Form state
  const [targetPlanId, setTargetPlanId] = useState<string>("null");
  const [effectiveAtMode, setEffectiveAtMode] = useState<string>("now");
  const [customEffectiveAt, setCustomEffectiveAt] = useState<string>(
    new Date().toISOString().substring(0, 16)
  );
  const [idempotencyKey, setIdempotencyKey] = useState<string>("");
  const [preview, setPreview] = useState<ProrationPreview | null>(null);
  const [apiResponse, setApiResponse] = useState<any | null>(null);

  // Admin Data State
  const [adminCustomers, setAdminCustomers] = useState<CustomerAdminView[]>([]);
  const [adminReconciliations, setAdminReconciliations] = useState<ReconciliationRecord[]>([]);
  const [adminLedger, setAdminLedger] = useState<LedgerEntry[]>([]);
  const [adminLogins, setAdminLogins] = useState<LoginAuditRecord[]>([]);
  
  // Admin search and filters state
  const [searchName, setSearchName] = useState("");
  const [searchEmail, setSearchEmail] = useState("");
  const [filterPlanId, setFilterPlanId] = useState("");
  const [filterStatus, setFilterStatus] = useState("");

  // Admin Ledger filters
  const [ledgerFilterType, setLedgerFilterType] = useState("");
  const [ledgerFilterStatus, setLedgerFilterStatus] = useState("");
  const [ledgerSort, setLedgerSort] = useState("desc");

  // Selected profile details for Admin view
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);
  const [selectedCustomerProfile, setSelectedCustomerProfile] = useState<any | null>(null);

  // Reconciliation resolving parameters
  const [resolvingRecordId, setResolvingRecordId] = useState<string | null>(null);
  const [resolutionNotes, setResolutionNotes] = useState<string>("");

  const [loading, setLoading] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<boolean>(false);


  // Fetch plans on boot
  useEffect(() => {
    fetchPlans();
  }, []);

  // Poll dashboard data based on role
  useEffect(() => {
    if (!session) return;
    loadRoleData();
    const interval = setInterval(() => {
      loadRoleData();
    }, 4000);
    return () => clearInterval(interval);
  }, [session, customerTab, adminTab, selectedCustomerId, searchName, searchEmail, filterPlanId, filterStatus, ledgerFilterType, ledgerFilterStatus, ledgerSort]);

  // Update proration preview
  useEffect(() => {
    if (session?.role === "CUSTOMER" && custSub) {
      fetchProrationPreview();
    }
  }, [targetPlanId, effectiveAtMode, customEffectiveAt, custSub?.plan_id]);

  const createIdempotencyKey = () => {
    // Financial mutations must be safe to retry. A fresh key is created for
    // each new operation and retained if the user retries the same request.
    return `plan_change_${crypto.randomUUID()}`;
  };

  const generateNewIdempotencyKey = () => {
    setIdempotencyKey(createIdempotencyKey());
  };

  useEffect(() => {
    if (!idempotencyKey) {
      generateNewIdempotencyKey();
    }
  }, [idempotencyKey]);

  const fetchPlans = async () => {
    try {
      const res = await fetch(`${baseUrl}/plans`);
      if (res.ok) setPlans(await res.json());
    } catch (err) {
      console.error("Failed to load plans", err);
    }
  };

  const loadRoleData = async () => {
    if (!session) return;
    const headers = { "Authorization": `Bearer ${session.token}` };
    try {
      if (session.role === "CUSTOMER") {
        const [subRes, ledgerRes, timelineRes] = await Promise.all([
          fetch(`${baseUrl}/customer/subscription`, { headers }),
          fetch(`${baseUrl}/customer/ledger`, { headers }),
          fetch(`${baseUrl}/customer/plan-changes`, { headers })
        ]);
        if (subRes.ok) setCustSub(await subRes.json());
        if (ledgerRes.ok) setCustLedger(await ledgerRes.json());
        if (timelineRes.ok) setCustTimeline(await timelineRes.json());
      } else if (session.role === "ADMIN") {
        // Build filters query
        let queryParams = [];
        if (searchName) queryParams.push(`name=${encodeURIComponent(searchName)}`);
        if (searchEmail) queryParams.push(`email=${encodeURIComponent(searchEmail)}`);
        if (filterPlanId) queryParams.push(`plan_id=${filterPlanId}`);
        if (filterStatus) queryParams.push(`status=${filterStatus}`);
        const queryStr = queryParams.length > 0 ? `?${queryParams.join("&")}` : "";

        // Build ledger query
        let ledgerParams = [];
        if (ledgerFilterType) ledgerParams.push(`type=${ledgerFilterType}`);
        if (ledgerFilterStatus) ledgerParams.push(`status=${ledgerFilterStatus}`);
        ledgerParams.push(`sort=${ledgerSort}`);
        const ledgerQueryStr = ledgerParams.length > 0 ? `?${ledgerParams.join("&")}` : "";

        const [custsRes, reconsRes, ledgerRes, loginsRes] = await Promise.all([
          fetch(`${baseUrl}/admin/customers${queryStr}`, { headers }),
          fetch(`${baseUrl}/admin/reconciliations`, { headers }),
          fetch(`${baseUrl}/admin/ledger${ledgerQueryStr}`, { headers }),
          fetch(`${baseUrl}/admin/login-history`, { headers })
        ]);

        if (custsRes.ok) setAdminCustomers(await custsRes.json());
        if (reconsRes.ok) setAdminReconciliations(await reconsRes.json());
        if (ledgerRes.ok) setAdminLedger(await ledgerRes.json());
        if (loginsRes.ok) setAdminLogins(await loginsRes.json());

        // Fetch selected customer profile details if open
        if (selectedCustomerId) {
          const profileRes = await fetch(`${baseUrl}/admin/customers/${selectedCustomerId}`, { headers });
          if (profileRes.ok) {
            setSelectedCustomerProfile(await profileRes.json());
          }
        }
      }
    } catch (err) {
      console.error("Data poll failure", err);
    }
  };

  const fetchProrationPreview = async () => {
    if (!session || !custSub) return;
    const headers = { "Authorization": `Bearer ${session.token}` };
    try {
      const effectiveAt = getCalculatedEffectiveAt();
      const planQuery = targetPlanId === "null" ? "" : `&to_plan_id=${targetPlanId}`;
      const res = await fetch(
        `${baseUrl}/customer/proration-preview?effective_at_str=${effectiveAt}${planQuery}`,
        { headers }
      );
      if (res.ok) setPreview(await res.json());
    } catch (err) {
      console.error("Preview fetch error", err);
    }
  };

  const getCalculatedEffectiveAt = (): string => {
    if (!custSub) return new Date().toISOString();
    const start = new Date(custSub.cycle_start).getTime();
    const end = new Date(custSub.cycle_end).getTime();

    switch (effectiveAtMode) {
      case "cycle_start":
        return custSub.cycle_start;
      case "cycle_end":
        return custSub.cycle_end;
      case "midpoint":
        return new Date(start + (end - start) / 2).toISOString();
      case "custom":
        return new Date(customEffectiveAt).toISOString();
      case "now":
      default:
        return new Date().toISOString();
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);
    if (authPassword !== authConfirmPassword) {
      setAuthError("Passwords do not match");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${baseUrl}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: authName,
          email: authEmail,
          password: authPassword,
          confirm_password: authConfirmPassword
        })
      });
      const data = await res.json();
      if (res.ok) {
        saveSession({
          token: data.access_token,
          role: data.role,
          email: authEmail,
          name: authName,
          customer_id: data.customer_id,
          subscription_id: data.subscription_id
        });
        resetAuthForm();
      } else {
        const errorMsg = Array.isArray(data.detail)
          ? data.detail.map((err: any) => `${err.loc[err.loc.length - 1]}: ${err.msg}`).join(", ")
          : (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail) || "Registration failed");
        setAuthError(errorMsg);
      }
    } catch (err: any) {
      setAuthError(err.message || "Network connection failed");
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);
    setLoading(true);
    try {
      const res = await fetch(`${baseUrl}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: authEmail, password: authPassword })
      });
      const data = await res.json();
      if (res.ok) {
        // Fetch details to get name
        const meHeaders = { "Authorization": `Bearer ${data.access_token}` };
        const meRes = await fetch(`${baseUrl}/auth/me`, { headers: meHeaders });
        const meData = await meRes.json();
        
        saveSession({
          token: data.access_token,
          role: data.role,
          email: authEmail,
          name: meData.customer_name || "Administrator",
          customer_id: data.customer_id,
          subscription_id: data.subscription_id
        });
        resetAuthForm();
      } else {
        const errorMsg = Array.isArray(data.detail)
          ? data.detail.map((err: any) => `${err.loc[err.loc.length - 1]}: ${err.msg}`).join(", ")
          : (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail) || "Authentication failed");
        setAuthError(errorMsg);
      }
    } catch (err: any) {
      setAuthError(err.message || "Network connection failed");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    if (!session) return;
    try {
      await fetch(`${baseUrl}/auth/logout`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${session.token}` }
      });
    } catch (err) {
      console.error("Logout failed at server", err);
    }
    localStorage.removeItem("prora_session");
    setSession(null);
    setCustSub(null);
    setCustLedger([]);
    setCustTimeline([]);
    setAdminCustomers([]);
    setSelectedCustomerId(null);
    setSelectedCustomerProfile(null);
  };

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordChangeMsg(null);
    if (newPassword !== confirmNewPassword) {
      setPasswordChangeMsg({ text: "New passwords do not match", success: false });
      return;
    }
    setActionLoading(true);
    try {
      const res = await fetch(`${baseUrl}/auth/change-password`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${session?.token}`
        },
        body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
      });
      const data = await res.json();
      if (res.ok) {
        setPasswordChangeMsg({ text: "Password changed successfully", success: true });
        setOldPassword("");
        setNewPassword("");
        setConfirmNewPassword("");
      } else {
        setPasswordChangeMsg({ text: data.detail || "Failed to update password", success: false });
      }
    } catch (err: any) {
      setPasswordChangeMsg({ text: err.message, success: false });
    } finally {
      setActionLoading(false);
    }
  };

  const handleApplyPlanChange = async () => {
    if (!session || !custSub) return;
    // This fallback also covers a user clicking before the initialization
    // effect has completed.
    const requestIdempotencyKey = idempotencyKey || createIdempotencyKey();
    if (!idempotencyKey) setIdempotencyKey(requestIdempotencyKey);
    setActionLoading(true);
    setApiResponse(null);
    try {
      const toPlan = targetPlanId === "null" ? null : targetPlanId;
      const res = await fetch(`${baseUrl}/customer/plan-changes`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${session.token}`,
          "Idempotency-Key": requestIdempotencyKey
        },
        body: JSON.stringify({ to_plan_id: toPlan })
      });

      const data = await res.json();
      setApiResponse({
        status: res.status,
        statusText: res.statusText,
        data
      });

      if (res.ok) {
        generateNewIdempotencyKey();
        loadRoleData();
      }
    } catch (err: any) {
      setApiResponse({
        status: 500,
        statusText: "Network Error",
        data: { detail: err.message }
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleSimulateWebhook = async (gatewayChargeId: string, eventType: string) => {
    setActionLoading(true);
    try {
      const res = await fetch(`${baseUrl}/mock/payments/${gatewayChargeId}/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_type: eventType })
      });
      if (res.ok) {
        loadRoleData();
      }
    } catch (err) {
      console.error("Webhook simulation failed:", err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleResolveReconciliation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resolvingRecordId || !session) return;
    setActionLoading(true);
    try {
      const res = await fetch(`${baseUrl}/admin/reconciliations/${resolvingRecordId}/resolve`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${session.token}`
        },
        body: JSON.stringify({ resolution_notes: resolutionNotes })
      });
      if (res.ok) {
        setResolvingRecordId(null);
        setResolutionNotes("");
        loadRoleData();
      }
    } catch (err) {
      console.error("Failed to resolve reconciliation:", err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleResetDatabase = async () => {
    if (!window.confirm("CRITICAL WARNING: This will drop all database tables, recreate them, and reseed all default data. Continue?")) return;
    if (!session) return;
    setActionLoading(true);
    try {
      const res = await fetch(`${baseUrl}/admin/system/reset`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${session.token}` }
      });
      if (res.ok) {
        alert("Database successfully reset and re-seeded!");
        handleLogout();
      } else {
        const d = await res.json();
        alert(`Reset failed: ${d.detail}`);
      }
    } catch (err: any) {
      alert(`Reset error: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const saveSession = (s: AuthSession) => {
    localStorage.setItem("prora_session", JSON.stringify(s));
    setSession(s);
  };

  const resetAuthForm = () => {
    setAuthName("");
    setAuthEmail("");
    setAuthPassword("");
    setAuthConfirmPassword("");
    setAuthError(null);
  };

  const formatCurrency = (cents: number): string => {
    return `₹${(cents / 100).toFixed(2)}`;
  };

  const formatDate = (isoString: string): string => {
    return new Date(isoString).toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      dateStyle: 'medium',
      timeStyle: 'short'
    });
  };

  // Rendering Loading overlay if auth process in action
  if (loading) {
    return (
      <div style={{ display: 'flex', height: '100vh', justifyContent: 'center', alignItems: 'center', backgroundColor: '#07080e', color: '#fff', fontFamily: 'sans-serif' }}>
        <h2>Authenticating with Prora Systems...</h2>
      </div>
    );
  }

  // 1. Auth Page View (Registration / Login)
  if (!session) {
    return (
      <div className="auth-container" style={{ 
        display: 'flex', 
        minHeight: '100vh', 
        width: '100%',
        position: 'relative',
        overflow: 'hidden',
        justifyContent: 'center', 
        alignItems: 'center', 
        backgroundImage: 'radial-gradient(rgba(255, 255, 255, 0.04) 1.5px, transparent 0), linear-gradient(rgba(7, 8, 14, 0.82), rgba(7, 8, 14, 0.82)), url(/bg.png)',
        backgroundSize: '24px 24px, 100% 100%, cover',
        backgroundPosition: 'center center, center center, center center',
        backgroundRepeat: 'repeat, no-repeat, no-repeat',
        backgroundAttachment: 'scroll, scroll, fixed',
        color: '#fff' 
      }}>
        <div className="ambient-glow-1"></div>
        <div className="ambient-glow-2"></div>
        <div className="card" style={{ width: '450px', padding: '2.5rem', boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5)', background: 'rgba(15, 17, 26, 0.85)', backdropFilter: 'blur(16px)', border: '1px solid rgba(255, 255, 255, 0.08)', zIndex: 10 }}>
          <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
            <h1 style={{ 
              fontFamily: 'Outfit', 
              fontSize: '2.4rem', 
              fontWeight: 800, 
              letterSpacing: '-0.5px', 
              background: 'linear-gradient(135deg, #ffffff 0%, #a78bfa 100%)', 
              WebkitBackgroundClip: 'text', 
              WebkitTextFillColor: 'transparent', 
              backgroundClip: 'text', 
              margin: '0',
              lineHeight: '1.2',
              padding: '4px 0'
            }}>PRORA</h1>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '4px' }}>Enterprise Subscription Billing Portal</div>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem', marginBottom: '1.5rem' }}>
            <button onClick={() => { setAuthTab("login_cust"); setAuthError(null); }} className="tab-btn" style={{ flex: 1, padding: '0.5rem', background: authTab === 'login_cust' ? 'var(--accent-light)' : 'transparent', color: authTab === 'login_cust' ? '#fff' : 'var(--text-muted)', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem' }}>Customer Login</button>
            <button onClick={() => { setAuthTab("register_cust"); setAuthError(null); }} className="tab-btn" style={{ flex: 1, padding: '0.5rem', background: authTab === 'register_cust' ? 'var(--accent-light)' : 'transparent', color: authTab === 'register_cust' ? '#fff' : 'var(--text-muted)', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem' }}>Register</button>
            <button onClick={() => { setAuthTab("login_admin"); setAuthError(null); }} className="tab-btn" style={{ flex: 1, padding: '0.5rem', background: authTab === 'login_admin' ? 'var(--accent-light)' : 'transparent', color: authTab === 'login_admin' ? '#fff' : 'var(--text-muted)', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem' }}>Admin Console</button>
          </div>

          {authError && (
            <div style={{ padding: '0.75rem 1rem', background: 'var(--danger-bg)', color: 'var(--danger)', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 600, marginBottom: '1rem', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
              {authError}
            </div>
          )}

          {authTab === "register_cust" ? (
            /* Register Customer Form */
            <form onSubmit={handleRegister} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div className="form-group">
                <label>Full Name / Company</label>
                <input type="text" placeholder="John Doe" value={authName} onChange={(e) => setAuthName(e.target.value)} className="form-input" required />
              </div>
              <div className="form-group">
                <label>Email Address</label>
                <input type="email" placeholder="user@company.com" value={authEmail} onChange={(e) => setAuthEmail(e.target.value)} className="form-input" required />
              </div>
              <div className="form-group">
                <label>Password (min 6 chars)</label>
                <input type="password" placeholder="••••••••" value={authPassword} onChange={(e) => setAuthPassword(e.target.value)} className="form-input" required />
              </div>
              <div className="form-group">
                <label>Confirm Password</label>
                <input type="password" placeholder="••••••••" value={authConfirmPassword} onChange={(e) => setAuthConfirmPassword(e.target.value)} className="form-input" required />
              </div>
              <button type="submit" className="btn-primary" style={{ marginTop: '0.5rem' }}>Sign Up & Onboard</button>
            </form>
          ) : (
            /* Customer Login & Admin Login Forms */
            <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div className="form-group">
                <label>Email Address</label>
                <input type="email" placeholder="user@company.com" value={authEmail} onChange={(e) => setAuthEmail(e.target.value)} className="form-input" required />
              </div>
              <div className="form-group">
                <label>Password</label>
                <input type="password" placeholder="••••••••" value={authPassword} onChange={(e) => setAuthPassword(e.target.value)} className="form-input" required />
              </div>
              <button type="submit" className="btn-primary" style={{ marginTop: '0.5rem' }}>
                {authTab === 'login_admin' ? "Access Admin Console" : "Log In"}
              </button>
              
              {authTab === 'login_admin' && (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center', marginTop: '0.5rem' }}>
                  Seed login: <code>admin@prora.com</code> / <code>adminpassword123</code>
                </div>
              )}
              {authTab === 'login_cust' && (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center', marginTop: '0.5rem' }}>
                  Seed login: <code>customer_a@prora.com</code> / <code>password123</code>
                </div>
              )}
            </form>
          )}
        </div>
      </div>
    );
  }

  // 2. Customer Portal Dashboard View
  if (session.role === "CUSTOMER") {
    if (!custSub) {
      return (
        <div style={{ display: 'flex', height: '100vh', justifyContent: 'center', alignItems: 'center', backgroundColor: '#07080e', color: '#fff', fontFamily: 'sans-serif' }}>
          <h2>Loading subscription details...</h2>
        </div>
      );
    }
    return (
      <div className="dashboard-container">
        <div className="ambient-glow-1"></div>
        <div className="ambient-glow-2"></div>
        <header className="dashboard-header">
          <div>
            <h1>PRORA <span style={{ fontWeight: 300, fontSize: '1.2rem', color: 'var(--text-muted)' }}>Customer Portal</span></h1>
            <div style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: "4px" }}>
              Welcome back, <b>{session.name}</b> ({session.email})
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1.2rem' }}>
            <div className="connection-status">
              <span className="pulse-dot"></span>
              <span>Active Session</span>
            </div>
            <button onClick={handleLogout} className="reset-btn" style={{ padding: '0.4rem 1rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--danger)', color: 'var(--danger)' }}>
              Sign Out
            </button>
          </div>
        </header>

        {/* Navigation Tabs */}
        <div style={{ padding: '0 2.5rem', marginTop: '1.5rem' }}>
          <div className="tab-navigation" style={{ display: 'flex', gap: '1rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem' }}>
            <button onClick={() => setCustomerTab("dashboard")} className={`tab-btn ${customerTab === 'dashboard' ? 'active' : ''}`} style={{ border: 'none', background: 'transparent', color: customerTab === 'dashboard' ? '#fff' : 'var(--text-muted)', padding: '0.6rem 1.2rem', cursor: 'pointer', fontWeight: 700 }}>
              Dashboard
            </button>
            <button onClick={() => setCustomerTab("ledger")} className={`tab-btn ${customerTab === 'ledger' ? 'active' : ''}`} style={{ border: 'none', background: 'transparent', color: customerTab === 'ledger' ? '#fff' : 'var(--text-muted)', padding: '0.6rem 1.2rem', cursor: 'pointer', fontWeight: 700 }}>
              Billing History
            </button>
            <button onClick={() => setCustomerTab("security")} className={`tab-btn ${customerTab === 'security' ? 'active' : ''}`} style={{ border: 'none', background: 'transparent', color: customerTab === 'security' ? '#fff' : 'var(--text-muted)', padding: '0.6rem 1.2rem', cursor: 'pointer', fontWeight: 700 }}>
              Account Settings
            </button>
          </div>
        </div>

        {customerTab === "dashboard" && (
          <main className="dashboard-body" style={{ padding: '2rem 2.5rem', display: 'grid', gridTemplateColumns: '1.1fr 0.9fr', gap: '2rem' }}>
            
            {/* Dashboard left column: Active subscription & Timeline */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
              {custSub && (
                <div className="card">
                  <h2 className="card-title">
                    My Active Subscription
                    <span className={`badge badge-${custSub.plan_id ? custSub.status.toLowerCase() : 'cancelled'}`} style={{ marginLeft: '0.5rem' }}>
                      {custSub.plan_id ? custSub.status : "NO ACTIVE PLAN"}
                    </span>
                  </h2>
                  {custSub.plan_id ? (
                    <div className="info-grid" style={{ marginBottom: '1.25rem' }}>
                      <div className="info-item">
                        <span className="info-label">Current Plan</span>
                        <span className="info-value" style={{ fontWeight: 800 }}>
                          {custSub.plan_name} ({formatCurrency(custSub.plan_price_cents)}/mo)
                        </span>
                      </div>
                      <div className="info-item">
                        <span className="info-label">Billing Cycle Version</span>
                        <span className="info-value">v{custSub.version}</span>
                      </div>
                      <div className="info-item" style={{ gridColumn: 'span 2' }}>
                        <span className="info-label">Active Period</span>
                        <span className="info-value">
                          {formatDate(custSub.cycle_start)} — {formatDate(custSub.cycle_end)}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div style={{ padding: '2rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.8rem', textAlign: 'center', background: 'rgba(255,255,255,0.01)', borderRadius: '12px', border: '1px dashed var(--border-color)' }}>
                      <span style={{ fontSize: '2rem' }}>💎</span>
                      <div style={{ fontWeight: 700, color: '#fff', fontSize: '1.1rem' }}>No Active Plan</div>
                      <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Choose one of our premium plans in the activation panel to get started!</div>
                    </div>
                  )}

                  {/* Visual progress bar */}
                  {custSub.plan_id && custSub.status !== "CANCELLED" && (
                    <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '1rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                        <span>Billing Cycle Progress</span>
                        <span>
                          {(() => {
                            const start = new Date(custSub.cycle_start).getTime();
                            const end = new Date(custSub.cycle_end).getTime();
                            const total = end - start;
                            const elapsed = Date.now() - start;
                            const percent = Math.min(100, Math.max(0, (elapsed / total) * 100));
                            return `${percent.toFixed(1)}%`;
                          })()}
                        </span>
                      </div>
                      <div style={{ height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', overflow: 'hidden' }}>
                        <div 
                          style={{ 
                            height: '100%', 
                            background: 'linear-gradient(90deg, var(--accent-color) 0%, var(--success) 100%)', 
                            width: (() => {
                              const start = new Date(custSub.cycle_start).getTime();
                              const end = new Date(custSub.cycle_end).getTime();
                              const total = end - start;
                              const elapsed = Date.now() - start;
                              return `${Math.min(100, Math.max(0, (elapsed / total) * 100))}%`;
                            })()
                          }}
                        ></div>
                      </div>
                    </div>
                  )}
                </div>
              )}
 
              {/* Visual Change Timeline Log */}
              <div className="card">
                <h2 className="card-title">Plan Timeline History</h2>
                {custTimeline.length === 0 ? (
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No subscription changes recorded.</div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    {custTimeline.map((pc) => {
                      let typeText = "Plan Change";
                      let subtitle = "";
                      const effectiveTime = new Date(pc.effective_at);
                      const cycleEndTime = custSub ? new Date(custSub.cycle_end) : new Date();
 
                      if (!pc.from_plan_id && pc.to_plan_id) {
                        typeText = "Subscription Initiated";
                        subtitle = `Activated subscription plan "${pc.to_plan_name}".`;
                      } else if (pc.from_plan_id && !pc.to_plan_id) {
                        typeText = "Subscription Cancelled";
                        subtitle = `Cancelled plan "${pc.from_plan_name}".`;
                      } else {
                        const net = pc.net_cents;
                        typeText = net > 0 ? "Plan Upgraded" : net < 0 ? "Plan Downgraded" : "Plan Updated";
                        subtitle = `Changed from "${pc.from_plan_name}" to "${pc.to_plan_name}".`;
                      }
 
                      return (
                        <div key={pc.id} style={{ 
                          borderLeft: `4px solid ${pc.status === 'CONFIRMED' ? 'var(--success)' : pc.status === 'SUPERSEDED' ? 'var(--info)' : 'var(--warning)'}`,
                          background: 'rgba(255, 255, 255, 0.01)',
                          padding: '1rem 1.25rem',
                          borderRadius: '0 8px 8px 0',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '0.4rem'
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontWeight: 700, fontSize: '0.95rem', color: '#fff' }}>{typeText}</span>
                            <span className={`badge badge-${pc.status.toLowerCase()}`}>{pc.status}</span>
                          </div>
                          
                          <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                            {subtitle}
                          </div>
 
                          {pc.status === 'CONFIRMED' && (
                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.25rem', borderTop: '1px solid rgba(255,255,255,0.03)', paddingTop: '0.4rem' }}>
                              <div>• Effective on: <b>{formatDate(pc.effective_at)}</b></div>
                              {pc.from_plan_id && (
                                <div>• Previous plan active until: <b>{formatDate(pc.effective_at)}</b></div>
                              )}
                              {pc.to_plan_id && custSub && (
                                <div>• Active from <b>{formatDate(pc.effective_at)}</b> until <b>{formatDate(custSub.cycle_end)}</b> ({Math.round(Math.max(0, (cycleEndTime.getTime() - effectiveTime.getTime()) / (1000 * 60 * 60 * 24)))} days remaining in cycle).</div>
                              )}
                              <div>• Financial impact: <b>{pc.net_cents > 0 ? `Charged ${formatCurrency(pc.net_cents)}` : pc.net_cents < 0 ? `Credited ${formatCurrency(Math.abs(pc.net_cents))}` : 'No net charge'}</b></div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
 
            {/* Dashboard right column: Plan Upgrade simulator */}
            <div>
              <div className="card">
                <h2 className="card-title">
                  {custSub.plan_id ? "Upgrade / Modify Plan" : "Activate Subscription"}
                </h2>
                <div className="simulator-form" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  
                  <div className="form-group">
                    <label>Choose Plan</label>
                    <select value={targetPlanId} onChange={(e) => setTargetPlanId(e.target.value)} className="form-select">
                      {custSub.plan_id ? (
                        <option value="null">None (Cancel Subscription)</option>
                      ) : (
                        <option value="null">-- Select a Plan --</option>
                      )}
                      {plans.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} — {formatCurrency(p.price_cents)}/mo
                        </option>
                      ))}
                    </select>
                  </div>
 
                  {custSub.plan_id && (
                    <div className="form-group">
                      <label>Effective Time of Change</label>
                      <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                        {[
                          { mode: "now", label: "Now" },
                          { mode: "cycle_start", label: "Cycle Start" },
                          { mode: "midpoint", label: "Mid-cycle" },
                          { mode: "cycle_end", label: "Cycle End" },
                          { mode: "custom", label: "Custom Date" }
                        ].map((item) => (
                          <button
                            key={item.mode}
                            type="button"
                            onClick={() => setEffectiveAtMode(item.mode)}
                            className="btn-action"
                            style={{
                              borderColor: effectiveAtMode === item.mode ? "var(--accent-color)" : "",
                              backgroundColor: effectiveAtMode === item.mode ? "var(--accent-light)" : ""
                            }}
                          >
                            {item.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
 
                  {custSub.plan_id && effectiveAtMode === "custom" && (
                    <div className="form-group">
                      <label>Custom Date (UTC)</label>
                      <input type="datetime-local" value={customEffectiveAt} onChange={(e) => setCustomEffectiveAt(e.target.value)} className="form-input" />
                    </div>
                  )}
 
                  {/* Proration Preview Breakdown Box */}
                  {preview && (
                    <div className="proration-breakdown" style={{ background: 'rgba(255,255,255,0.02)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                      <div style={{ fontWeight: 700, fontSize: "0.8rem", textTransform: "uppercase", color: "var(--accent-color)", marginBottom: '0.5rem' }}>
                        {custSub.plan_id ? "Prorated Preview" : "Checkout Preview"}
                      </div>
                      {custSub.plan_id && (
                        <>
                          <div className="breakdown-row" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.4rem' }}>
                            <span>Remaining Period:</span>
                            <span>{(preview.remaining_ratio * 100).toFixed(1)}%</span>
                          </div>
                          <div className="breakdown-row" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.4rem' }}>
                            <span>Unused Value (Credit):</span>
                            <span style={{ color: 'var(--success)' }}>-{formatCurrency(preview.credit_cents)}</span>
                          </div>
                        </>
                      )}
                      <div className="breakdown-row" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.4rem' }}>
                        <span>New Plan Charge:</span>
                        <span>+{formatCurrency(preview.charge_cents)}</span>
                      </div>
                      <div className="breakdown-row total" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem', fontWeight: 800, borderTop: '1px solid var(--border-color)', paddingTop: '0.4rem', marginTop: '0.4rem' }}>
                        <span>Net Due Amount:</span>
                        <span style={{ color: preview.net_cents > 0 ? 'var(--warning)' : 'var(--success)' }}>
                          {formatCurrency(preview.net_cents)}
                        </span>
                      </div>
                    </div>
                  )}
 
                  {custSub && (targetPlanId === (custSub.plan_id || "null")) && (
                    <div style={{ color: 'var(--warning)', fontSize: '0.85rem', fontWeight: 600, textAlign: 'center', marginTop: '0.25rem' }}>
                      ⚠️ Subscription is already on this plan.
                    </div>
                  )}
 
                  <button
                    onClick={handleApplyPlanChange}
                    className="btn-primary"
                    disabled={actionLoading || !custSub || (targetPlanId === (custSub.plan_id || "null")) || (custSub.status === "CANCELLED" && targetPlanId === "null")}
                  >
                    {actionLoading 
                      ? "Requesting..." 
                      : (custSub && targetPlanId === (custSub.plan_id || "null")) 
                        ? "Already on this plan" 
                        : custSub.plan_id 
                          ? "Confirm Plan Change" 
                          : "Activate Subscription"}
                  </button>
                </div>

                {apiResponse && (
                  <div style={{ marginTop: '1rem', padding: '1rem', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid var(--border-color)', borderRadius: '8px', fontSize: '0.8rem' }}>
                    <div style={{ fontWeight: 700, marginBottom: '0.25rem' }}>Response State: {apiResponse.status}</div>
                    <pre style={{ overflowX: 'auto', margin: 0, color: apiResponse.status >= 400 ? 'var(--danger)' : 'var(--success)' }}>
                      {JSON.stringify(apiResponse.data, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            </div>

          </main>
        )}

        {customerTab === "ledger" && (
          <main className="dashboard-body" style={{ padding: '2rem 2.5rem' }}>
            <div className="card">
              <h2 className="card-title">Auditable Billing History</h2>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
                All transaction records posted to your account are audited here. Records are read-only.
              </div>
              <div className="ledger-table-container">
                {custLedger.length === 0 ? (
                  <div style={{ color: 'var(--text-muted)', padding: '1rem' }}>No transaction records found.</div>
                ) : (
                  <table className="ledger-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Type</th>
                        <th>Amount</th>
                        <th>Status</th>
                        <th>Reference details</th>
                      </tr>
                    </thead>
                    <tbody>
                      {custLedger.map((entry) => (
                        <tr key={entry.id}>
                          <td>{formatDate(entry.created_at)}</td>
                          <td style={{ fontWeight: 700, color: entry.type === 'CHARGE' ? 'var(--warning)' : 'var(--success)' }}>
                            {entry.type}
                          </td>
                          <td>{formatCurrency(entry.amount_cents)}</td>
                          <td>
                            <span className={`badge badge-${entry.status.toLowerCase()}`}>
                              {entry.status}
                            </span>
                          </td>
                          <td>
                            {entry.is_reconciliation ? "Reconciliation Adjustment Record" : "Regular subscription billing charge"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </main>
        )}

        {customerTab === "security" && (
          <main className="dashboard-body" style={{ padding: '2rem 2.5rem', display: 'flex', justifyContent: 'center' }}>
            <div className="card" style={{ width: '500px' }}>
              <h2 className="card-title">Security & Account Settings</h2>
              
              <div style={{ marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Registered Email</div>
                <div style={{ fontWeight: 700, fontSize: '1rem', marginTop: '0.2rem' }}>{session.email}</div>
              </div>

              {passwordChangeMsg && (
                <div style={{ 
                  padding: '0.75rem 1rem', 
                  background: passwordChangeMsg.success ? 'var(--success-bg)' : 'var(--danger-bg)',
                  color: passwordChangeMsg.success ? 'var(--success)' : 'var(--danger)',
                  borderRadius: '6px',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  marginBottom: '1rem'
                }}>
                  {passwordChangeMsg.text}
                </div>
              )}

              <form onSubmit={handlePasswordChange} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div className="form-group">
                  <label>Current Password</label>
                  <input type="password" value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} className="form-input" required />
                </div>
                <div className="form-group">
                  <label>New Password (min 6 chars)</label>
                  <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className="form-input" required />
                </div>
                <div className="form-group">
                  <label>Confirm New Password</label>
                  <input type="password" value={confirmNewPassword} onChange={(e) => setConfirmNewPassword(e.target.value)} className="form-input" required />
                </div>
                <button type="submit" className="btn-primary" disabled={actionLoading || !oldPassword || !newPassword}>
                  {actionLoading ? "Updating..." : "Update Account Password"}
                </button>
              </form>
            </div>
          </main>
        )}
      </div>
    );
  }

  // 3. Admin Console Dashboard View
  if (session.role === "ADMIN") {
    return (
      <div className="dashboard-container">
        <div className="ambient-glow-1"></div>
        <div className="ambient-glow-2"></div>
        <header className="dashboard-header">
          <div>
            <h1>PRORA <span style={{ fontWeight: 300, fontSize: '1.2rem', color: 'var(--text-muted)' }}>Admin Console</span></h1>
            <div style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: "4px" }}>
              Administrator Active Session: <b>{session.email}</b>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1.2rem' }}>
            <div className="connection-status" style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid var(--accent-color)' }}>
              <span className="pulse-dot" style={{ backgroundColor: 'var(--accent-color)', boxShadow: '0 0 8px var(--accent-color)' }}></span>
              <span style={{ color: 'var(--accent-hover)' }}>Admin Access</span>
            </div>
            <button onClick={handleLogout} className="reset-btn" style={{ padding: '0.4rem 1rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--danger)', color: 'var(--danger)' }}>
              Sign Out
            </button>
          </div>
        </header>

        {/* Sidebar + Main workspace */}
        <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', minHeight: 'calc(100vh - 80px)' }}>
          {/* Admin Sidebar Navigation */}
          <aside style={{ backgroundColor: 'rgba(15, 17, 26, 0.5)', borderRight: '1px solid var(--border-color)', padding: '1.5rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            {[
              { id: "overview", label: "📊 Overview" },
              { id: "customers", label: "👥 Customer Profiles" },
              { id: "reconciliations", label: "⚠️ Reconciliations" },
              { id: "ledger", label: "📖 General Ledger" },
              { id: "logins", label: "🔑 Login Audit Log" },
              { id: "webhooks", label: "⚙️ Webhook Simulators" },
              { id: "system", label: "⚙️ System Controls" }
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  setAdminTab(tab.id as any);
                  setSelectedCustomerId(null);
                  setSelectedCustomerProfile(null);
                }}
                className={`tab-btn`}
                style={{
                  textAlign: 'left',
                  padding: '0.75rem 1rem',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  background: adminTab === tab.id ? 'var(--accent-color)' : 'transparent',
                  color: adminTab === tab.id ? '#fff' : 'var(--text-muted)',
                  display: 'block',
                  width: '100%'
                }}
              >
                {tab.label}
              </button>
            ))}
          </aside>

          {/* Admin Workspace */}
          <main style={{ padding: '2rem 2.5rem', overflowY: 'auto' }}>
            
            {adminTab === "overview" && (
              <div>
                <h2 style={{ fontFamily: 'Outfit', fontSize: '1.5rem', marginBottom: '1.5rem' }}>Platform Overview</h2>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.5rem', marginBottom: '2rem' }}>
                  <div className="card" style={{ padding: '1.5rem', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>TOTAL CUSTOMERS</div>
                    <div style={{ fontSize: '2rem', fontWeight: 800, marginTop: '0.4rem', color: 'var(--accent-hover)' }}>{adminCustomers.length}</div>
                  </div>
                  <div className="card" style={{ padding: '1.5rem', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>ACTIVE SUBSCRIPTIONS</div>
                    <div style={{ fontSize: '2rem', fontWeight: 800, marginTop: '0.4rem', color: 'var(--success)' }}>
                      {adminCustomers.filter(c => c.status === "ACTIVE").length}
                    </div>
                  </div>
                  <div className="card" style={{ padding: '1.5rem', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>RECONCILIATION TASKS</div>
                    <div style={{ fontSize: '2rem', fontWeight: 800, marginTop: '0.4rem', color: 'var(--danger)' }}>
                      {adminReconciliations.filter(r => r.status === "PENDING").length}
                    </div>
                  </div>
                  <div className="card" style={{ padding: '1.5rem', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>POSTED REVENUE</div>
                    <div style={{ fontSize: '2rem', fontWeight: 800, marginTop: '0.4rem', color: 'var(--warning)' }}>
                      {formatCurrency(adminLedger.filter(e => e.type === "CHARGE" && e.status === "POSTED").reduce((sum, e) => sum + e.amount_cents, 0))}
                    </div>
                  </div>
                </div>

                <div className="card">
                  <h3 className="card-title">Recent Platform Actions</h3>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
                    Audit trail of recent general ledger bookings across all customer accounts.
                  </div>
                  <div className="ledger-table-container" style={{ maxHeight: '300px' }}>
                    <table className="ledger-table" style={{ fontSize: '0.8rem' }}>
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Customer</th>
                          <th>Type</th>
                          <th>Amount</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {adminLedger.slice(0, 5).map((e, idx) => (
                          <tr key={idx}>
                            <td>{formatDate(e.created_at)}</td>
                            <td><b>{e.customer_name}</b></td>
                            <td style={{ color: e.type === 'CHARGE' ? 'var(--warning)' : 'var(--success)' }}>{e.type}</td>
                            <td>{formatCurrency(e.amount_cents)}</td>
                            <td><span className={`badge badge-${e.status.toLowerCase()}`}>{e.status}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {adminTab === "customers" && (
              <div>
                {!selectedCustomerId ? (
                  /* 1. Full-Width Customer Directory Table */
                  <div className="card">
                    <h2 className="card-title">Customer Directory</h2>
                    
                    {/* Filters Toolbar */}
                    <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1.25rem' }}>
                      <div className="form-group" style={{ flex: 1, minWidth: '150px' }}>
                        <label>Search Name</label>
                        <input type="text" value={searchName} onChange={(e) => setSearchName(e.target.value)} placeholder="e.g. Startup" className="form-input" />
                      </div>
                      <div className="form-group" style={{ flex: 1, minWidth: '150px' }}>
                        <label>Search Email</label>
                        <input type="text" value={searchEmail} onChange={(e) => setSearchEmail(e.target.value)} placeholder="e.g. customer" className="form-input" />
                      </div>
                      <div className="form-group" style={{ width: '150px' }}>
                        <label>Plan Filter</label>
                        <select value={filterPlanId} onChange={(e) => setFilterPlanId(e.target.value)} className="form-select">
                          <option value="">All Plans</option>
                          {plans.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                        </select>
                      </div>
                      <div className="form-group" style={{ width: '150px' }}>
                        <label>Status Filter</label>
                        <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)} className="form-select">
                          <option value="">All Statuses</option>
                          <option value="ACTIVE">ACTIVE</option>
                          <option value="CANCELLED">CANCELLED</option>
                        </select>
                      </div>
                    </div>

                    <div className="ledger-table-container">
                      {adminCustomers.length === 0 ? (
                        <div style={{ color: 'var(--text-muted)', padding: '1rem' }}>No customers match the search criteria.</div>
                      ) : (
                        <table className="ledger-table">
                          <thead>
                            <tr>
                              <th>Customer Name</th>
                              <th>Email Address</th>
                              <th>Account Created</th>
                              <th>Active Plan</th>
                              <th>Subscription Status</th>
                              <th>Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {adminCustomers.map((c) => (
                              <tr key={c.id}>
                                <td><b>{c.name}</b></td>
                                <td>{c.email}</td>
                                <td>{formatDate(c.created_at)}</td>
                                <td>{c.plan_name}</td>
                                <td>
                                  <span className={`badge badge-${c.status.toLowerCase()}`}>
                                    {c.status}
                                  </span>
                                </td>
                                <td>
                                  <button onClick={() => setSelectedCustomerId(c.id)} className="btn-action" style={{ borderColor: 'var(--accent-color)', color: 'var(--accent-hover)' }}>
                                    View Profile & History
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  </div>
                ) : (
                  /* 2. Side-by-Side Split Console Layout */
                  <div style={{ display: 'flex', gap: '2rem', height: '75vh', overflow: 'hidden' }}>
                    
                    {/* Left Pane: Customer List with Quick Search */}
                    <div className="card" style={{ width: '320px', flexShrink: 0, overflowY: 'auto', padding: '1.25rem' }}>
                      <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.1rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem' }}>
                        Profiles
                      </h3>
                      <div className="form-group" style={{ marginBottom: '1rem' }}>
                        <input 
                          type="text" 
                          placeholder="Quick search..." 
                          value={searchName} 
                          onChange={(e) => setSearchName(e.target.value)} 
                          className="form-input" 
                          style={{ padding: '0.5rem 0.75rem', fontSize: '0.85rem' }} 
                        />
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        {adminCustomers.map((c) => (
                          <div 
                            key={c.id} 
                            onClick={() => setSelectedCustomerId(c.id)}
                            style={{
                              padding: '0.75rem 1rem',
                              borderRadius: '8px',
                              cursor: 'pointer',
                              background: selectedCustomerId === c.id ? 'var(--accent-light)' : 'rgba(255,255,255,0.02)',
                              border: `1px solid ${selectedCustomerId === c.id ? 'var(--accent-color)' : 'transparent'}`,
                              transition: 'all 0.2s ease',
                              display: 'flex',
                              flexDirection: 'column',
                              gap: '0.2rem'
                            }}
                          >
                            <span style={{ fontWeight: 700, fontSize: '0.85rem', color: '#fff' }}>{c.name}</span>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                              <span>{c.plan_name}</span>
                              <span style={{ color: c.status === 'ACTIVE' ? 'var(--success)' : 'var(--danger)' }}>{c.status}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Right Pane: Selected Customer Sub-Tab Workspace */}
                    <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                      
                      {selectedCustomerProfile ? (
                        <div className="card" style={{ flex: 1, padding: '1.5rem' }}>
                          
                          {/* Profile Header card info */}
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem', marginBottom: '1rem' }}>
                            <div>
                              <h2 style={{ margin: '0', fontFamily: 'Outfit', fontSize: '1.4rem', color: '#fff' }}>
                                {selectedCustomerProfile.name}
                              </h2>
                              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                                Account Email: <b>{selectedCustomerProfile.email}</b> | Created: {formatDate(selectedCustomerProfile.created_at)}
                              </div>
                            </div>
                            <button 
                              onClick={() => { setSelectedCustomerId(null); setSelectedCustomerProfile(null); }} 
                              className="btn-action" 
                              style={{ borderColor: 'var(--danger)', color: 'var(--danger)' }}
                            >
                              Close Details ✕
                            </button>
                          </div>

                          {/* Profile workspace content */}
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                            
                            {/* Current Subscription parameters */}
                            {selectedCustomerProfile.subscription ? (
                              <div style={{ background: 'rgba(255,255,255,0.01)', padding: '1.25rem', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
                                <h4 style={{ margin: '0 0 0.8rem 0', color: 'var(--accent-hover)', fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                                  Subscription Status
                                </h4>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', fontSize: '0.85rem' }}>
                                  <div>
                                    <span style={{ color: 'var(--text-muted)', display: 'block' }}>Plan</span>
                                    <b>{selectedCustomerProfile.subscription.plan_name} ({formatCurrency(selectedCustomerProfile.subscription.plan_price_cents)}/mo)</b>
                                  </div>
                                  <div>
                                    <span style={{ color: 'var(--text-muted)', display: 'block' }}>Active Cycle</span>
                                    <b>{formatDate(selectedCustomerProfile.subscription.cycle_start)}</b>
                                  </div>
                                  <div>
                                    <span style={{ color: 'var(--text-muted)', display: 'block' }}>Ends On</span>
                                    <b>{formatDate(selectedCustomerProfile.subscription.cycle_end)}</b>
                                  </div>
                                  <div>
                                    <span style={{ color: 'var(--text-muted)', display: 'block' }}>Status</span>
                                    <span className={`badge badge-${selectedCustomerProfile.subscription.status.toLowerCase()}`}>
                                      {selectedCustomerProfile.subscription.status}
                                    </span>
                                  </div>
                                </div>
                              </div>
                            ) : (
                              <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No active subscription profile.</div>
                            )}

                            {/* Section: Posted Ledger and Changes side-by-side */}
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                              
                              {/* Ledger Entries column */}
                              <div>
                                <h4 style={{ margin: '0 0 0.6rem 0', fontSize: '0.95rem', color: '#fff' }}>Customer Ledger (Recent)</h4>
                                <div className="ledger-table-container" style={{ maxHeight: '180px' }}>
                                  <table className="ledger-table" style={{ fontSize: '0.75rem' }}>
                                    <thead>
                                      <tr>
                                        <th>Date</th>
                                        <th>Type</th>
                                        <th>Amount</th>
                                        <th>Status</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {selectedCustomerProfile.ledger.map((e: any, idx: number) => (
                                        <tr key={idx}>
                                          <td>{formatDate(e.created_at)}</td>
                                          <td style={{ color: e.type === 'CHARGE' ? 'var(--warning)' : 'var(--success)', fontWeight: 700 }}>{e.type}</td>
                                          <td>{formatCurrency(e.amount_cents)}</td>
                                          <td><span className={`badge badge-${e.status.toLowerCase()}`} style={{ padding: '0.15rem 0.4rem', fontSize: '0.65rem' }}>{e.status}</span></td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              </div>

                              {/* Plan Changes list timeline */}
                              <div>
                                <h4 style={{ margin: '0 0 0.6rem 0', fontSize: '0.95rem', color: '#fff' }}>Subscription Timeline</h4>
                                <div style={{ maxHeight: '180px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                                  {selectedCustomerProfile.plan_changes.length === 0 ? (
                                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No modifications.</div>
                                  ) : (
                                    selectedCustomerProfile.plan_changes.map((pc: any) => (
                                      <div key={pc.id} style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border-color)', padding: '0.6rem 0.8rem', borderRadius: '6px', fontSize: '0.75rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <div>
                                          <span style={{ fontWeight: 700 }}>{pc.from_plan_name} ➔ {pc.to_plan_name}</span>
                                          <div style={{ color: 'var(--text-muted)', fontSize: '0.65rem', marginTop: '2px' }}>
                                            {formatDate(pc.requested_at)}
                                          </div>
                                        </div>
                                        <span className={`badge badge-${pc.status.toLowerCase()}`} style={{ padding: '0.15rem 0.4rem', fontSize: '0.65rem' }}>{pc.status}</span>
                                      </div>
                                    ))
                                  )}
                                </div>
                              </div>

                            </div>

                            {/* Section: Logins and Reconciliations */}
                            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '1.5rem' }}>
                              
                              {/* Login audits */}
                              <div>
                                <h4 style={{ margin: '0 0 0.6rem 0', fontSize: '0.95rem', color: '#fff' }}>Login Audit Trail</h4>
                                <div className="ledger-table-container" style={{ maxHeight: '150px' }}>
                                  <table className="ledger-table" style={{ fontSize: '0.75rem' }}>
                                    <thead>
                                      <tr>
                                        <th>Timestamp</th>
                                        <th>Status</th>
                                        <th>IP / Agent</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {selectedCustomerProfile.logins.map((l: any, idx: number) => (
                                        <tr key={idx}>
                                          <td>{formatDate(l.login_at)}</td>
                                          <td>
                                            <span style={{ color: l.success ? 'var(--success)' : 'var(--danger)', fontWeight: 700 }}>
                                              {l.success ? "SUCCESS" : "FAILED"}
                                            </span>
                                          </td>
                                          <td style={{ color: 'var(--text-muted)', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', maxWidth: '140px' }}>
                                            {l.ip_address || "—"} ({l.user_agent ? l.user_agent.substring(0, 15) : "—"}...)
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              </div>

                              {/* Reconciliations box */}
                              <div>
                                <h4 style={{ margin: '0 0 0.6rem 0', fontSize: '0.95rem', color: '#fff' }}>Dispute Actions</h4>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', maxHeight: '150px', overflowY: 'auto' }}>
                                  {selectedCustomerProfile.reconciliations.length === 0 ? (
                                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No anomalies flagged.</div>
                                  ) : (
                                    selectedCustomerProfile.reconciliations.map((r: any) => (
                                      <div key={r.id} style={{ padding: '0.5rem 0.75rem', borderRadius: '6px', borderLeft: `3px solid ${r.status === 'PENDING' ? 'var(--danger)' : 'var(--success)'}`, background: 'rgba(255,255,255,0.01)', fontSize: '0.75rem' }}>
                                        <div style={{ fontWeight: 700 }}>{r.reason}</div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', fontSize: '0.65rem', marginTop: '2px' }}>
                                          <span>{formatCurrency(r.amount_cents)}</span>
                                          <span style={{ color: r.status === 'PENDING' ? 'var(--warning)' : 'var(--success)' }}>{r.status}</span>
                                        </div>
                                      </div>
                                    ))
                                  )}
                                </div>
                              </div>

                            </div>

                          </div>
                        </div>
                      ) : (
                        <div className="card" style={{ display: 'flex', height: '100%', justifyContent: 'center', alignItems: 'center', color: 'var(--text-muted)' }}>
                          Select a customer profile to inspect details.
                        </div>
                      )}

                    </div>
                  </div>
                )}
              </div>
            )}

            {adminTab === "reconciliations" && (
              <div className="card">
                <h2 className="card-title">Manual Reconciliation Manager</h2>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
                  A list of all transaction records flagged for manual reconciliation (e.g. late captures on superseded or cancelled plan changes).
                </div>
                <div className="ledger-table-container">
                  {adminReconciliations.length === 0 ? (
                    <div style={{ color: 'var(--text-muted)', padding: '1rem' }}>No reconciliation records found.</div>
                  ) : (
                    <table className="ledger-table">
                      <thead>
                        <tr>
                          <th>Date Flagged</th>
                          <th>Reference</th>
                          <th>Reason</th>
                          <th>Amount</th>
                          <th>Status</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {adminReconciliations.map((r) => (
                          <tr key={r.id} style={{ backgroundColor: r.status === 'PENDING' ? 'rgba(239, 68, 68, 0.02)' : 'transparent' }}>
                            <td>{formatDate(r.created_at)}</td>
                            <td><code>{r.merchant_reference}</code></td>
                            <td>{r.reason}</td>
                            <td>{formatCurrency(r.amount_cents)}</td>
                            <td><span className={`badge badge-${r.status.toLowerCase()}`}>{r.status}</span></td>
                            <td>
                              {r.status === "PENDING" ? (
                                <div>
                                  {resolvingRecordId === r.id ? (
                                    <form onSubmit={handleResolveReconciliation} style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', marginTop: '0.5rem' }}>
                                      <input type="text" placeholder="Resolution notes..." value={resolutionNotes} onChange={(e) => setResolutionNotes(e.target.value)} className="form-input" style={{ padding: '0.3rem', fontSize: '0.8rem' }} required />
                                      <div style={{ display: 'flex', gap: '0.4rem' }}>
                                        <button type="submit" className="btn-action" style={{ borderColor: 'var(--success)', color: 'var(--success)', fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}>Confirm</button>
                                        <button type="button" onClick={() => setResolvingRecordId(null)} className="btn-action" style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}>Cancel</button>
                                      </div>
                                    </form>
                                  ) : (
                                    <button onClick={() => { setResolvingRecordId(r.id); setResolutionNotes(""); }} className="btn-action" style={{ borderColor: 'var(--danger)', color: 'var(--danger)', fontSize: '0.8rem' }}>
                                      Resolve Manually
                                    </button>
                                  )}
                                </div>
                              ) : (
                                <div style={{ fontSize: '0.8rem', color: 'var(--success)' }}>
                                  <i>Resolved: {r.resolution_notes}</i>
                                </div>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            )}

            {adminTab === "ledger" && (
              <div className="card">
                <h2 className="card-title">General Auditable Financial Ledger</h2>
                
                {/* Ledger filters toolbar */}
                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1.25rem' }}>
                  <div className="form-group" style={{ width: '150px' }}>
                    <label>Entry Type</label>
                    <select value={ledgerFilterType} onChange={(e) => setLedgerFilterType(e.target.value)} className="form-select">
                      <option value="">All Types</option>
                      <option value="CHARGE">CHARGE</option>
                      <option value="CREDIT">CREDIT</option>
                    </select>
                  </div>
                  <div className="form-group" style={{ width: '150px' }}>
                    <label>Posting Status</label>
                    <select value={ledgerFilterStatus} onChange={(e) => setLedgerFilterStatus(e.target.value)} className="form-select">
                      <option value="">All Statuses</option>
                      <option value="PENDING">PENDING</option>
                      <option value="POSTED">POSTED</option>
                      <option value="REVERSED">REVERSED</option>
                    </select>
                  </div>
                  <div className="form-group" style={{ width: '150px' }}>
                    <label>Sort Date</label>
                    <select value={ledgerSort} onChange={(e) => setLedgerSort(e.target.value)} className="form-select">
                      <option value="desc">Newest First</option>
                      <option value="asc">Oldest First</option>
                    </select>
                  </div>
                </div>

                <div className="ledger-table-container">
                  {adminLedger.length === 0 ? (
                    <div style={{ color: 'var(--text-muted)', padding: '1rem' }}>No ledger entries logged.</div>
                  ) : (
                    <table className="ledger-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Customer</th>
                          <th>Type</th>
                          <th>Amount</th>
                          <th>Status</th>
                          <th>Attributes</th>
                        </tr>
                      </thead>
                      <tbody>
                        {adminLedger.map((entry, idx) => (
                          <tr key={idx}>
                            <td>{formatDate(entry.created_at)}</td>
                            <td><b>{entry.customer_name}</b></td>
                            <td style={{ fontWeight: 700, color: entry.type === 'CHARGE' ? 'var(--warning)' : 'var(--success)' }}>{entry.type}</td>
                            <td>{formatCurrency(entry.amount_cents)}</td>
                            <td><span className={`badge badge-${entry.status.toLowerCase()}`}>{entry.status}</span></td>
                            <td>
                              {entry.is_reconciliation && (
                                <span className="badge badge-unknown" style={{ fontSize: '0.7rem' }}>RECONCILIATION</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            )}

            {adminTab === "logins" && (
              <div className="card">
                <h2 className="card-title">Authentication Activity Audit Trail</h2>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
                  Auditable logging of all authentication events, successful logins, and failed verification attempts.
                </div>
                <div className="ledger-table-container">
                  {adminLogins.length === 0 ? (
                    <div style={{ color: 'var(--text-muted)', padding: '1rem' }}>No auth records tracked.</div>
                  ) : (
                    <table className="ledger-table" style={{ fontSize: '0.85rem' }}>
                      <thead>
                        <tr>
                          <th>Time</th>
                          <th>Email Address Attempted</th>
                          <th>Status</th>
                          <th>IP Address</th>
                          <th>Browser Agent</th>
                          <th>Failure Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {adminLogins.map((l) => (
                          <tr key={l.id} style={{ backgroundColor: !l.success ? 'rgba(239, 68, 68, 0.02)' : 'transparent' }}>
                            <td>{formatDate(l.login_at)}</td>
                            <td><b>{l.email_attempted}</b></td>
                            <td>
                              <span className={`badge badge-${l.success ? 'succeeded' : 'failed'}`}>
                                {l.success ? "SUCCESS" : "FAILED"}
                              </span>
                            </td>
                            <td>{l.ip_address || "—"}</td>
                            <td style={{ maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.user_agent || "—"}</td>
                            <td style={{ color: 'var(--danger)', fontWeight: 600 }}>{l.failure_reason || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            )}

            {adminTab === "webhooks" && (
              <div className="card">
                <h2 className="card-title">Mock Webhook Console</h2>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
                  Trigger webhook events from the payment gateway to test processing and state machine determinism.
                </div>
                <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
                  💡 To see pending charges, register a customer user, log in, select the Pro or Premium plan, and choose a change effective now. The charge will appear here as <b>PENDING</b>.
                </div>

                {/* Iterate through all customers' pending payments */}
                {adminCustomers.map((cust) => {
                  return (
                    <CustomerPendingPayments key={cust.id} customerId={cust.id} customerName={cust.name} baseUrl={baseUrl} token={session.token} formatCurrency={formatCurrency} handleSimulateWebhook={handleSimulateWebhook} />
                  );
                })}
              </div>
            )}

            {adminTab === "system" && (
              <div className="card" style={{ borderColor: 'var(--danger)' }}>
                <h2 className="card-title" style={{ color: 'var(--danger)' }}>Dangerous System Controls</h2>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
                  Wipe out all current records, drop all tables, recreate them, and restore the baseline configuration of seeded admin and demo customer credentials.
                </div>
                <button onClick={handleResetDatabase} className="reset-btn" style={{ padding: '1rem', width: '100%', fontSize: '1rem' }} disabled={actionLoading}>
                  {actionLoading ? "Processing System reset..." : "Execute Complete DB Schema Wipe & Re-seed"}
                </button>
              </div>
            )}

          </main>
        </div>
      </div>
    );
  }

  return null;
}

/* Sub-component to fetch and display pending payments for a specific customer in Webhooks tab */
interface PendingPaymentsProps {
  customerId: string;
  customerName: string;
  baseUrl: string;
  token: string;
  formatCurrency: (cents: number) => string;
  handleSimulateWebhook: (chargeId: string, eventType: string) => Promise<void>;
}

function CustomerPendingPayments({ customerId, customerName, baseUrl, token, formatCurrency, handleSimulateWebhook }: PendingPaymentsProps) {
  const [profile, setProfile] = useState<any | null>(null);

  useEffect(() => {
    fetchProfile();
  }, [customerId]);

  const fetchProfile = async () => {
    try {
      const res = await fetch(`${baseUrl}/admin/customers/${customerId}`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (res.ok) setProfile(await res.json());
    } catch (err) {
      console.error(err);
    }
  };

  if (!profile || profile.payments.length === 0) return null;

  const pendingPayments = profile.payments.filter((p: any) => p.status === "PENDING" && p.gateway_charge_id);

  if (pendingPayments.length === 0) return null;

  return (
    <div style={{ marginBottom: '1.5rem', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1rem', background: 'rgba(255,255,255,0.01)' }}>
      <h3 style={{ fontSize: '1rem', margin: '0 0 0.75rem 0', fontFamily: 'Outfit' }}>Pending Payments for: <b>{customerName}</b></h3>
      {pendingPayments.map((p: any) => (
        <div key={p.id} className="payment-item" style={{ background: 'rgba(255,255,255,0.02)', padding: '0.85rem', borderRadius: '6px', marginBottom: '0.5rem', border: '1px solid rgba(255,255,255,0.03)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.4rem' }}>
            <span>Charge Ref: <code>{p.merchant_reference}</code></span>
            <span style={{ fontWeight: 800, color: 'var(--warning)' }}>{formatCurrency(p.amount_cents)}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Gateway Charge: <code>{p.gateway_charge_id}</code></span>
            <div style={{ display: 'flex', gap: '0.4rem' }}>
              <button onClick={async () => { await handleSimulateWebhook(p.gateway_charge_id, "SUCCESS"); fetchProfile(); }} className="btn-action" style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem', borderColor: 'var(--success)', color: 'var(--success)' }}>SUCCESS</button>
              <button onClick={async () => { await handleSimulateWebhook(p.gateway_charge_id, "FAILURE"); fetchProfile(); }} className="btn-action" style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem', borderColor: 'var(--danger)', color: 'var(--danger)' }}>FAILURE</button>
              <button onClick={async () => { await handleSimulateWebhook(p.gateway_charge_id, "DELAYED_SUCCESS"); fetchProfile(); }} className="btn-action" style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}>DELAYED</button>
              <button onClick={async () => { await handleSimulateWebhook(p.gateway_charge_id, "DUPLICATE_SUCCESS"); fetchProfile(); }} className="btn-action" style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}>DUPLICATE (3x)</button>
              <button onClick={async () => { await handleSimulateWebhook(p.gateway_charge_id, "OUT_OF_ORDER"); fetchProfile(); }} className="btn-action" style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}>OUT-OF-ORDER</button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default App;
