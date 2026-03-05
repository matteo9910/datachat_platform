import React, { useState, useEffect } from 'react';
import { brandApi, BrandConfig } from '../../api/brandApi';
import { useAuth } from '../../contexts/AuthContext';
import { Toast, useToast } from '../ui/toast';

const FONT_OPTIONS = [
  'Inter, system-ui, sans-serif',
  'Roboto, sans-serif',
  'Open Sans, sans-serif',
  'Lato, sans-serif',
  'Montserrat, sans-serif',
  'Poppins, sans-serif',
  'Nunito, sans-serif',
  'Raleway, sans-serif',
  'Arial, Helvetica, sans-serif',
  'Georgia, serif',
  'Times New Roman, serif',
];

const BrandSettings: React.FC = () => {
  const { hasRole } = useAuth();
  const isAdmin = hasRole(['admin']);
  const { toast, showToast, hideToast } = useToast();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [primaryColor, setPrimaryColor] = useState('#1f77b4');
  const [secondaryColor, setSecondaryColor] = useState('#ff7f0e');
  const [accentColorsText, setAccentColorsText] = useState('');
  const [fontFamily, setFontFamily] = useState('Inter, system-ui, sans-serif');
  const [logoUrl, setLogoUrl] = useState('');

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const config: BrandConfig = await brandApi.getConfig();
      setPrimaryColor(config.primary_color);
      setSecondaryColor(config.secondary_color);
      setAccentColorsText(config.accent_colors.join(', '));
      setFontFamily(config.font_family);
      setLogoUrl(config.logo_url || '');
    } catch (error) {
      console.error('Error loading brand config:', error);
      showToast('Errore nel caricamento della configurazione brand', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!isAdmin) return;
    setSaving(true);
    try {
      // Parse accent colors from comma-separated text
      const accentColors = accentColorsText
        .split(',')
        .map((c) => c.trim())
        .filter((c) => c.length > 0);

      await brandApi.saveConfig({
        primary_color: primaryColor,
        secondary_color: secondaryColor,
        accent_colors: accentColors.length > 0 ? accentColors : undefined,
        font_family: fontFamily,
        logo_url: logoUrl || undefined,
      });
      showToast('Configurazione brand salvata con successo!', 'success');
    } catch (error: unknown) {
      const errMsg =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail ||
            'Errore nel salvataggio'
          : 'Errore nel salvataggio';
      showToast(errMsg, 'error');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <div className="flex items-center justify-center py-8">
          <div className="w-6 h-6 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-6">
      <Toast message={toast.message} type={toast.type} isVisible={toast.isVisible} onClose={hideToast} />

      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 bg-pink-100 rounded-xl flex items-center justify-center">
          <svg className="w-5 h-5 text-pink-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
          </svg>
        </div>
        <div>
          <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">Brand &amp; Colori Grafici</h3>
          <p className="text-xs text-slate-500">Colori e font applicati a tutti i grafici e dashboard</p>
        </div>
      </div>

      <div className="space-y-5">
        {/* Primary & Secondary Colors */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1.5">Colore Primario</label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={primaryColor}
                onChange={(e) => setPrimaryColor(e.target.value)}
                disabled={!isAdmin}
                className="w-10 h-10 rounded-lg border border-slate-300 cursor-pointer disabled:opacity-50"
              />
              <input
                type="text"
                value={primaryColor}
                onChange={(e) => setPrimaryColor(e.target.value)}
                disabled={!isAdmin}
                className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-sm font-mono focus:border-orange-500 focus:ring-1 focus:ring-orange-500 outline-none disabled:bg-slate-50 disabled:text-slate-400"
                placeholder="#1f77b4"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1.5">Colore Secondario</label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={secondaryColor}
                onChange={(e) => setSecondaryColor(e.target.value)}
                disabled={!isAdmin}
                className="w-10 h-10 rounded-lg border border-slate-300 cursor-pointer disabled:opacity-50"
              />
              <input
                type="text"
                value={secondaryColor}
                onChange={(e) => setSecondaryColor(e.target.value)}
                disabled={!isAdmin}
                className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-sm font-mono focus:border-orange-500 focus:ring-1 focus:ring-orange-500 outline-none disabled:bg-slate-50 disabled:text-slate-400"
                placeholder="#ff7f0e"
              />
            </div>
          </div>
        </div>

        {/* Accent Colors */}
        <div>
          <label className="block text-xs font-bold text-slate-700 mb-1.5">Colori Accent (hex, separati da virgola)</label>
          <input
            type="text"
            value={accentColorsText}
            onChange={(e) => setAccentColorsText(e.target.value)}
            disabled={!isAdmin}
            className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm font-mono focus:border-orange-500 focus:ring-1 focus:ring-orange-500 outline-none disabled:bg-slate-50 disabled:text-slate-400"
            placeholder="#2ca02c, #d62728, #9467bd"
          />
          {/* Preview swatches */}
          <div className="flex gap-1.5 mt-2 flex-wrap">
            <div className="w-6 h-6 rounded-md border border-slate-200" style={{ backgroundColor: primaryColor }} title="Primary" />
            <div className="w-6 h-6 rounded-md border border-slate-200" style={{ backgroundColor: secondaryColor }} title="Secondary" />
            {accentColorsText
              .split(',')
              .map((c) => c.trim())
              .filter((c) => /^#[0-9a-fA-F]{6}$/.test(c))
              .map((color, i) => (
                <div key={i} className="w-6 h-6 rounded-md border border-slate-200" style={{ backgroundColor: color }} title={color} />
              ))}
          </div>
        </div>

        {/* Font Family */}
        <div>
          <label className="block text-xs font-bold text-slate-700 mb-1.5">Font Family</label>
          <select
            value={fontFamily}
            onChange={(e) => setFontFamily(e.target.value)}
            disabled={!isAdmin}
            className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:border-orange-500 focus:ring-1 focus:ring-orange-500 outline-none bg-white disabled:bg-slate-50 disabled:text-slate-400"
          >
            {FONT_OPTIONS.map((font) => (
              <option key={font} value={font} style={{ fontFamily: font }}>
                {font.split(',')[0]}
              </option>
            ))}
          </select>
          <p className="text-xs text-slate-400 mt-1" style={{ fontFamily }}>
            Anteprima: Il quick brown fox jumps over the lazy dog
          </p>
        </div>

        {/* Logo URL */}
        <div>
          <label className="block text-xs font-bold text-slate-700 mb-1.5">Logo URL (opzionale)</label>
          <input
            type="text"
            value={logoUrl}
            onChange={(e) => setLogoUrl(e.target.value)}
            disabled={!isAdmin}
            className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:border-orange-500 focus:ring-1 focus:ring-orange-500 outline-none disabled:bg-slate-50 disabled:text-slate-400"
            placeholder="https://example.com/logo.png"
          />
        </div>

        {/* Save Button */}
        {isAdmin && (
          <button
            onClick={handleSave}
            disabled={saving}
            className="w-full py-3 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 disabled:opacity-50 transition-all"
          >
            {saving ? 'Salvataggio...' : 'Salva Configurazione Brand'}
          </button>
        )}

        {!isAdmin && (
          <p className="text-xs text-slate-400 text-center italic">
            Solo gli amministratori possono modificare la configurazione brand.
          </p>
        )}
      </div>
    </div>
  );
};

export default BrandSettings;