import React, { useEffect, useState, useRef } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { databaseApi } from "../api/databaseApi";

const OAuthCallback: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("Completamento autenticazione...");
  const calledRef = useRef(false);

  useEffect(() => {
    // Previeni doppia chiamata (React Strict Mode)
    if (calledRef.current) return;
    calledRef.current = true;

    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const error = searchParams.get("error");

    console.log("OAuth Callback - code:", code, "state:", state);

    if (error) {
      setStatus("error");
      setMessage(`Errore OAuth: ${error}`);
      return;
    }

    if (!code || !state) {
      setStatus("error");
      setMessage("Parametri OAuth mancanti");
      return;
    }

    // Scambia il code per i token
    databaseApi.oauthCallback(code, state)
      .then((result) => {
        console.log("OAuth callback success:", result);
        setStatus("success");
        setMessage("Autenticazione completata!");
        
        // Notifica il parent window (se in popup)
        if (window.opener) {
          window.opener.postMessage({ type: "oauth_success" }, "*");
          setTimeout(() => window.close(), 1000);
        } else {
          setTimeout(() => navigate("/"), 1500);
        }
      })
      .catch((err) => {
        console.error("OAuth callback error:", err);
        setStatus("error");
        setMessage(err.response?.data?.detail || "Errore durante autenticazione");
      });
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow-lg p-8 max-w-md w-full text-center">
        {status === "loading" && (
          <>
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-500 mx-auto mb-4"></div>
            <p className="text-slate-600">{message}</p>
          </>
        )}
        
        {status === "success" && (
          <>
            <div className="w-12 h-12 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-emerald-600 font-semibold">{message}</p>
            <p className="text-slate-400 text-sm mt-2">Chiusura automatica...</p>
          </>
        )}
        
        {status === "error" && (
          <>
            <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <p className="text-red-600 font-semibold">{message}</p>
            <button 
              onClick={() => window.close()}
              className="mt-4 px-4 py-2 bg-slate-100 rounded-lg text-slate-600 hover:bg-slate-200"
            >
              Chiudi
            </button>
          </>
        )}
      </div>
    </div>
  );
};

export default OAuthCallback;
