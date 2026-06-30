"""
Standalone 300V drift analysis script.
Generates gain_error_300V_drift_analysis.html from TDMS data.
Run from the workspace root (where NI-Emerson.jpg lives).
"""
import os, re, base64
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from nptdms import TdmsFile
from sklearn.linear_model import LinearRegression

# ── Configuration ─────────────────────────────────────────────────────────────
ROOT_PATH            = r'C:\temp\EnvironmentalTesting\Round2Data'
OUTPUT_HTML_300V_DRIFT = 'gain_error_300V_drift_analysis.html'
GAIN_ERROR_LIMIT_PPM = 100
LOGO_PATH            = 'NI-Emerson.jpg'

with open(LOGO_PATH, 'rb') as f:
    LOGO_BASE64 = base64.b64encode(f.read()).decode('utf-8')
print(f'Logo loaded ({len(LOGO_BASE64)} bytes base64)')

# ── Helpers ───────────────────────────────────────────────────────────────────
def parse_filename(filename):
    name = filename[:-5].strip()
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'\s+(AM|PM)$', r'_\1', name)
    name = name.replace('RH_Set_ ', 'RH_Set_')
    pattern = re.compile(
        r'^(?P<serial>[^_]+)_Temp_Set_(?P<temp>[^_]+)_RH_Set_(?P<rh>\d+)_'
        r'(?P<month>\d+)_(?P<day>\d+)_(?P<year>\d+)_'
        r'(?P<hour>\d+)_(?P<minute>\d+)_(?P<second>\d+)_(?P<am_pm>AM|PM)$'
    )
    match = pattern.match(name)
    if not match:
        raise ValueError(f'Unable to parse: {filename}')
    m = match
    dt = datetime(int(m.group('year')), int(m.group('month')), int(m.group('day')),
                  int(m.group('hour')), int(m.group('minute')), int(m.group('second')))
    am_pm = m.group('am_pm')
    hour  = int(m.group('hour'))
    if am_pm == 'PM' and hour != 12:
        dt = dt.replace(hour=hour + 12)
    elif am_pm == 'AM' and hour == 12:
        dt = dt.replace(hour=0)
    return m.group('serial'), m.group('temp'), m.group('rh'), dt

def serial_sort_key(serial):
    n = str(serial).strip()
    if n.lower().startswith('0x'):
        n = n[2:]
    try:
        return (0, int(n, 16), str(serial))
    except ValueError:
        return (1, str(serial))

def compute_gain_error_ppm(test_points, dut_meas):
    X = np.asarray(test_points).reshape(-1, 1)
    y = np.asarray(dut_meas)
    reg = LinearRegression().fit(X, y)
    return (reg.coef_[0] - 1) * 1_000_000

def _to_rgba(rgba):
    r, g, b, a = rgba
    return f'rgba({int(r * 255)},{int(g * 255)},{int(b * 255)},{a:.3f})'

def inject_branding_header(html_file_path, logo_base64_data):
    with open(html_file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    html_content = re.sub(
        r'<!-- NI_CONFIDENTIAL_HEADER_START -->[\s\S]*?<!-- NI_CONFIDENTIAL_HEADER_END -->\s*',
        '', html_content, flags=re.IGNORECASE)
    branding_html = f"""
<!-- NI_CONFIDENTIAL_HEADER_START -->
<div id="ni-confidential-header" style="padding: 16px 24px 14px; border-bottom: 2px solid #d0d0d0; margin-bottom: 14px; background: #fff;">
  <div style="display: flex; align-items: flex-start; justify-content: space-between;">
    <img src="data:image/jpeg;base64,{logo_base64_data}" alt="NI/Emerson Logo" style="height: 58px; width: auto; object-fit: contain;">
    <div style="flex: 1; text-align: center; margin-right: 58px;">
      <h1 style="color: #c62828; font-size: 24px; margin: 0 0 8px 0; font-weight: 700;">NI Confidential</h1>
      <p style="color: #111; font-size: 14px; margin: 0; line-height: 1.35;">
        This document contains proprietary information of NI/Emerson and is intended for internal use only. Unauthorized distribution is prohibited.
      </p>
    </div>
  </div>
</div>
<!-- NI_CONFIDENTIAL_HEADER_END -->
"""
    body_match = re.search(r'<body[^>]*>', html_content, flags=re.IGNORECASE)
    if body_match:
        insert_at = body_match.end()
        html_content = html_content[:insert_at] + '\n' + branding_html + '\n' + html_content[insert_at:]
    else:
        html_content = branding_html + '\n' + html_content
    with open(html_file_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

# ── Load TDMS data (300V range only, from 2026-06-20 18:00 onward) ───────────
start_300v = pd.Timestamp('2026-06-20 18:00:00')

tdms_files = []
for subdir in os.listdir(ROOT_PATH):
    sp = os.path.join(ROOT_PATH, subdir)
    if not os.path.isdir(sp):
        continue
    for fname in os.listdir(sp):
        if fname.endswith('.tdms'):
            tdms_files.append((sp, fname))

total = len(tdms_files)
print(f'Found {total} TDMS files.')

test_cands = ['Test Points 300V', 'Test Points']
dut_cands  = ['DUT Measurements 300V', 'DUT Measurements']

data = []
for idx, (sp, fname) in enumerate(tdms_files, 1):
    if idx % 5000 == 0 or idx == total:
        print(f'\r[{idx}/{total}]', end='', flush=True)
    try:
        serial, temp_set, rh_set, ts = parse_filename(fname)
        if ts < start_300v:
            continue
        fp = os.path.join(sp, fname)
        tf = TdmsFile.read(fp)
        grp = tf.groups()[0]
        tc = next((c for c in test_cands if c in grp), None)
        dc = next((c for c in dut_cands  if c in grp), None)
        if tc is None or dc is None:
            continue
        tp = grp[tc][:]
        dm = grp[dc][:]
        ge = compute_gain_error_ppm(tp, dm)
        if abs(ge) > GAIN_ERROR_LIMIT_PPM:
            continue
        data.append({'timestamp': ts, 'serial': serial, 'gain_error': ge, 'range': '300V'})
    except Exception as e:
        pass

print(f'\nLoaded {len(data)} rows.')

df = pd.DataFrame(data).sort_values(['serial', 'timestamp']).reset_index(drop=True)
if df.empty:
    raise ValueError('No 300V data loaded.')

t_min_300v = df['timestamp'].min()
df['hours'] = (df['timestamp'] - t_min_300v).dt.total_seconds() / 3600.0

print(f'Window: {t_min_300v}  to  {df["timestamp"].max()}')
print(f'Span: {df["hours"].max():.1f} h  |  Serials: {sorted(df["serial"].unique())}')

# ── Curve fit model: 2-parameter power law on NORMALISED data  ───────────────
# Fitting directly to the zero-anchored (normalised) data solves two problems:
#   1. The 3-parameter (A, β, d) absolute fit was underdetermined over a 158 h
#      window → optimizer found degenerate solutions (large A, β≈0) that look
#      flat and don't track the actual curve at all.
#   2. The normalised fit residuals are minimised in the same space that is
#      displayed in Figure 2, so the fit is guaranteed to land on the data.
#
# Model: ΔE(t) = A · (t^β − t_first^β)
#   • Zero at t = t_first by construction — no baseline ambiguity.
#   • Absolute plot: shift by y_first (the actual first measurement).
#   • Physical basis: Fick's 2nd law → moisture uptake ∝ t^β, β=0.5 ideal,
#     β<0.5 anomalous diffusion in a polymer/oxide thin film.
FIT_MIN_H = 50.0

serials_300v = sorted(df['serial'].unique(), key=serial_sort_key)
colormap_300v = plt.get_cmap('tab20' if len(serials_300v) > 10 else 'tab10')
serial_colors_300v = {ser: _to_rgba(colormap_300v(i % colormap_300v.N))
                      for i, ser in enumerate(serials_300v)}

fit_style = dict(color='rgba(128, 0, 128, 0.85)', dash='dot')

max_data_hours_300v = float(df['hours'].max())
forecast_end_300v   = max(90 * 24, max_data_hours_300v)

x_fit_linear = np.linspace(0, forecast_end_300v, 800)
x_fit_log    = np.logspace(-2, np.log10(forecast_end_300v), 800)

norm_coeffs = {}   # {ser: (A, beta, t_first, y_first)}

def _power_norm(t, A, beta, t_first):
    """A · (t^β − t_first^β) — zero at t=t_first by construction."""
    safe_t      = np.where(t > 0, t, 1e-10)
    safe_tfirst = max(t_first, 1e-10)
    return A * (np.power(safe_t, beta) - safe_tfirst ** beta)

# ── Figure 1: Absolute gain error ─────────────────────────────────────────────
fig1 = make_subplots(
    rows=2, cols=1,
    subplot_titles=('Gain Error vs. Time (Linear Scale)',
                    'Gain Error vs. Time (Log Scale)'),
    vertical_spacing=0.12,
)

for ser in serials_300v:
    sd = df[df['serial'] == ser].sort_values('hours')
    if len(sd) < 3:
        continue
    x_d    = sd['hours'].values
    y_d    = sd['gain_error'].values
    y_first = float(y_d[0])
    t_first = float(x_d[0])

    # Normalised data (zero-anchored to first measurement)
    y_norm_d = y_d - y_first

    # Fit window: t >= FIT_MIN_H applied to the normalised data
    mask    = x_d >= FIT_MIN_H
    x_fd    = x_d[mask]    if mask.sum() >= 20 else x_d
    y_nfd   = y_norm_d[mask] if mask.sum() >= 20 else y_norm_d

    # Build a per-serial 2-parameter model with t_first fixed
    def _make_model(tf):
        def model(t, A, beta):
            return _power_norm(t, A, beta, tf)
        return model
    fit_model = _make_model(t_first)

    # Data-driven initial guess: log-log slope of normalised values in window
    t0f, t1f = x_fd[0], x_fd[-1]
    y0f = float(np.median(y_nfd[:max(1, len(y_nfd)//10)]))
    y1f = float(np.median(y_nfd[-max(1, len(y_nfd)//10):]))
    y0f = max(y0f, 0.5)
    y1f = max(y1f, y0f + 0.1)
    beta0 = float(np.clip(
        np.log(y1f / y0f) / np.log(t1f / t0f) if t1f > t0f else 0.35,
        0.05, 0.95))
    denom0 = max(t0f ** beta0 - t_first ** beta0, 1e-6)
    A0 = max(y0f / denom0, 0.01)

    popt = None
    for p0_try in [[A0, beta0], [A0, 0.5], [A0, 0.3], [A0 * 0.5, 0.4]]:
        try:
            candidate, _ = curve_fit(
                fit_model, x_fd, y_nfd,
                p0=p0_try,
                bounds=([0, 0.05], [np.inf, 1.0]),
                maxfev=20000,
            )
            # Accept only if the fit's range over the data window is at least
            # half the observed normalised range (reject near-flat degenerate fits)
            y_check = fit_model(x_fd, *candidate)
            if (y_check.max() - y_check.min()) >= 0.5 * max(y_nfd.max() - y_nfd.min(), 0.1):
                popt = candidate
                break
        except Exception:
            pass

    # Fallback: if all guesses fail the quality gate, use the first convergent
    if popt is None:
        for p0_try in [[A0, beta0], [A0, 0.5], [A0, 0.3]]:
            try:
                popt, _ = curve_fit(
                    fit_model, x_fd, y_nfd,
                    p0=p0_try,
                    bounds=([0, 0.05], [np.inf, 1.0]),
                    maxfev=20000,
                )
                break
            except Exception:
                popt = None

    if popt is not None:
        norm_coeffs[ser] = (*popt, t_first, y_first)
    fit_ok = popt is not None

    col = serial_colors_300v[ser]
    for row in [1, 2]:
        fig1.add_trace(go.Scatter(
            x=x_d, y=y_d, mode='markers',
            name=f'{ser} (raw)', showlegend=(row == 1), legendgroup=ser,
            marker=dict(size=5, color=col, opacity=0.55),
            hovertemplate=f'{ser}<br>Hours: %{{x:.1f}}<br>Gain Error: %{{y:.2f}} ppm<extra></extra>',
        ), row=row, col=1)
    if fit_ok:
        A_f, beta_f = popt
        y_lin_abs = _power_norm(x_fit_linear, A_f, beta_f, t_first) + y_first
        y_log_abs = _power_norm(x_fit_log,    A_f, beta_f, t_first) + y_first
        for row, xv, yv in [(1, x_fit_linear, y_lin_abs), (2, x_fit_log, y_log_abs)]:
            fig1.add_trace(go.Scatter(
                x=xv, y=yv, mode='lines',
                name=f'{ser} (t\u1d5d fit)', showlegend=(row == 1),
                legendgroup=f'{ser}_h', line=dict(**fit_style),
                hovertemplate=f'{ser}<br>Hours: %{{x:.0f}}<br>Fit: %{{y:.2f}} ppm<extra></extra>',
            ), row=row, col=1)

for row in [1, 2]:
    fig1.add_vline(x=max_data_hours_300v, line_dash='dash', line_color='grey',
                   annotation_text='End of measured data',
                   annotation_position='top right', row=row, col=1)

fig1.update_layout(title='PXIe-4080 300V Gain Error - Drift Analysis & 90-Day Forecast (Post Jun 20)',
                   height=1000, hovermode='x unified',
                   legend=dict(x=1.02, y=1, bgcolor='rgba(255,255,255,0.7)'))
fig1.update_xaxes(title_text='Hours (linear)', row=1, col=1, range=[0, forecast_end_300v])
fig1.update_xaxes(title_text='Hours (log scale)', row=2, col=1,
                  type='log', range=[-2, np.log10(forecast_end_300v)])
fig1.update_yaxes(title_text='Gain Error (ppm)', row=1, col=1)
fig1.update_yaxes(title_text='Gain Error (ppm)', row=2, col=1)

# ── Figure 2: Offset-normalised ───────────────────────────────────────────────
fig2 = make_subplots(
    rows=2, cols=1,
    subplot_titles=('Offset-Normalised Gain Error vs. Time (Linear Scale)',
                    'Offset-Normalised Gain Error vs. Time (Log Scale)'),
    vertical_spacing=0.12,
)

for ser in serials_300v:
    sd = df[df['serial'] == ser].sort_values('hours')
    if len(sd) < 3:
        continue
    x_d    = sd['hours'].values
    y_d    = sd['gain_error'].values
    y_norm = y_d - float(y_d[0])

    col = serial_colors_300v[ser]
    for row in [1, 2]:
        fig2.add_trace(go.Scatter(
            x=x_d, y=y_norm, mode='markers',
            name=ser, showlegend=(row == 1), legendgroup=ser,
            marker=dict(size=5, color=col, opacity=0.55),
            hovertemplate=f'{ser}<br>Hours: %{{x:.1f}}<br>\u0394 Gain Error: %{{y:.2f}} ppm<extra></extra>',
        ), row=row, col=1)
    if ser in norm_coeffs:
        A_f, beta_f, t_first, _ = norm_coeffs[ser]
        y_lin_n = _power_norm(x_fit_linear, A_f, beta_f, t_first)
        y_log_n = _power_norm(x_fit_log,    A_f, beta_f, t_first)
        for row, xv, yv in [(1, x_fit_linear, y_lin_n), (2, x_fit_log, y_log_n)]:
            fig2.add_trace(go.Scatter(
                x=xv, y=yv, mode='lines',
                name=f'{ser} (t\u1d5d fit)', showlegend=(row == 1),
                legendgroup=f'{ser}_hn', line=dict(**fit_style),
                hovertemplate=f'{ser}<br>Hours: %{{x:.0f}}<br>\u0394 Fit: %{{y:.2f}} ppm<extra></extra>',
            ), row=row, col=1)

for row in [1, 2]:
    fig2.add_vline(x=max_data_hours_300v, line_dash='dash', line_color='grey',
                   annotation_text='End of measured data',
                   annotation_position='top right', row=row, col=1)

fig2.update_layout(title='PXIe-4080 300V Gain Error - Offset-Normalised Drift (Post Jun 20)',
                   height=1000, hovermode='x unified',
                   legend=dict(x=1.02, y=1, bgcolor='rgba(255,255,255,0.7)'))
fig2.update_xaxes(title_text='Hours (linear)', row=1, col=1, range=[0, forecast_end_300v])
fig2.update_xaxes(title_text='Hours (log scale)', row=2, col=1,
                  type='log', range=[-2, np.log10(forecast_end_300v)])
fig2.update_yaxes(title_text='\u0394 Gain Error (ppm)', row=1, col=1)
fig2.update_yaxes(title_text='\u0394 Gain Error (ppm)', row=2, col=1)

# ── Figure 1: Absolute gain error ─────────────────────────────────────────────
fig1 = make_subplots(
    rows=2, cols=1,
    subplot_titles=('Gain Error vs. Time (Linear Scale)',
                    'Gain Error vs. Time (Log Scale)'),
    vertical_spacing=0.12,
)

for ser in serials_300v:
    sd = df[df['serial'] == ser].sort_values('hours')
    if len(sd) < 3:
        continue
    x_d = sd['hours'].values
    y_d = sd['gain_error'].values

    # Fit only on t >= FIT_MIN_H (early transient has decayed by then).
    mask = x_d >= FIT_MIN_H
    x_fd = x_d[mask] if mask.sum() >= 20 else x_d
    y_fd = y_d[mask] if mask.sum() >= 20 else y_d

    # Data-driven initial guess for (A, beta, d).
    # Estimate d from data before t=5h (before the humidity transient settles).
    early_mask = x_d < 5.0
    d0 = float(np.median(y_d[early_mask])) if early_mask.sum() >= 3 else float(y_d[0])
    # Estimate beta from log-log slope of (y - d) vs t in the fit window.
    t0f, t1f = x_fd[0], x_fd[-1]
    y0f = float(np.median(y_fd[:max(1, len(y_fd)//10)]))
    y1f = float(np.median(y_fd[-max(1, len(y_fd)//10):]))
    dy0, dy1 = max(y0f - d0, 0.1), max(y1f - d0, 0.1)
    beta0 = float(np.clip(
        np.log(dy1 / dy0) / np.log(t1f / t0f) if t1f > t0f else 0.4,
        0.05, 0.95))
    A0 = dy0 / max(t0f ** beta0, 1e-6)

    popt = None
    for p0_try, bnd in [
        ([A0,   beta0,     d0],   ([0, 0.01, -np.inf], [np.inf, 1.0, np.inf])),
        ([A0,   0.5,       d0],   ([0, 0.01, -np.inf], [np.inf, 1.0, np.inf])),
        ([A0,   0.3,       d0],   ([0, 0.01, -np.inf], [np.inf, 1.0, np.inf])),
        ([A0,   beta0, float(y_d[0])],
                                  ([0, 0.01, -np.inf], [np.inf, 1.0, np.inf])),
    ]:
        try:
            popt, _ = curve_fit(power_model, x_fd, y_fd, p0=p0_try,
                                bounds=bnd, maxfev=20000)
            break
        except Exception:
            popt = None
    if popt is not None:
        power_coeffs[ser] = popt
    fit_ok = popt is not None

    col = serial_colors_300v[ser]
    for row in [1, 2]:
        fig1.add_trace(go.Scatter(
            x=x_d, y=y_d, mode='markers',
            name=f'{ser} (raw)', showlegend=(row == 1), legendgroup=ser,
            marker=dict(size=5, color=col, opacity=0.55),
            hovertemplate=f'{ser}<br>Hours: %{{x:.1f}}<br>Gain Error: %{{y:.2f}} ppm<extra></extra>',
        ), row=row, col=1)
    if fit_ok:
        y_lin = power_model(x_fit_linear, *popt)
        y_log = power_model(x_fit_log, *popt)
        for row, xv, yv in [(1, x_fit_linear, y_lin), (2, x_fit_log, y_log)]:
            fig1.add_trace(go.Scatter(
                x=xv, y=yv, mode='lines',
                name=f'{ser} (t\u1d5d fit)', showlegend=(row == 1),
                legendgroup=f'{ser}_h', line=dict(**fit_style),
                hovertemplate=f'{ser}<br>Hours: %{{x:.0f}}<br>Fit: %{{y:.2f}} ppm<extra></extra>',
            ), row=row, col=1)

for row in [1, 2]:
    fig1.add_vline(x=max_data_hours_300v, line_dash='dash', line_color='grey',
                   annotation_text='End of measured data',
                   annotation_position='top right', row=row, col=1)

fig1.update_layout(title='PXIe-4080 300V Gain Error - Drift Analysis & 90-Day Forecast (Post Jun 20)',
                   height=1000, hovermode='x unified',
                   legend=dict(x=1.02, y=1, bgcolor='rgba(255,255,255,0.7)'))
fig1.update_xaxes(title_text='Hours (linear)', row=1, col=1, range=[0, forecast_end_300v])
fig1.update_xaxes(title_text='Hours (log scale)', row=2, col=1,
                  type='log', range=[-2, np.log10(forecast_end_300v)])
fig1.update_yaxes(title_text='Gain Error (ppm)', row=1, col=1)
fig1.update_yaxes(title_text='Gain Error (ppm)', row=2, col=1)

# ── Figure 2: Offset-normalised ───────────────────────────────────────────────
fig2 = make_subplots(
    rows=2, cols=1,
    subplot_titles=('Offset-Normalised Gain Error vs. Time (Linear Scale)',
                    'Offset-Normalised Gain Error vs. Time (Log Scale)'),
    vertical_spacing=0.12,
)

for ser in serials_300v:
    sd = df[df['serial'] == ser].sort_values('hours')
    if len(sd) < 3:
        continue
    x_d    = sd['hours'].values
    y_d    = sd['gain_error'].values
    # Normalise to the actual first measurement so raw scatter and fit both
    # start at 0 at t=x_d[0] — no model extrapolation to t≈0 required.
    actual_first_ge = float(y_d[0])
    y_norm = y_d - actual_first_ge
    col = serial_colors_300v[ser]
    for row in [1, 2]:
        fig2.add_trace(go.Scatter(
            x=x_d, y=y_norm, mode='markers',
            name=ser, showlegend=(row == 1), legendgroup=ser,
            marker=dict(size=5, color=col, opacity=0.55),
            hovertemplate=f'{ser}<br>Hours: %{{x:.1f}}<br>\u0394 Gain Error: %{{y:.2f}} ppm<extra></extra>',
        ), row=row, col=1)
    if ser in power_coeffs:
        popt = power_coeffs[ser]
        # Anchor the fit line to the actual first measurement so it starts at 0
        # at t=x_d[0], exactly matching the raw normalised scatter.
        baseline = float(power_model(np.array([x_d[0]]), *popt)[0])
        y_lin_n  = power_model(x_fit_linear, *popt) - baseline
        y_log_n  = power_model(x_fit_log,    *popt) - baseline
        for row, xv, yv in [(1, x_fit_linear, y_lin_n), (2, x_fit_log, y_log_n)]:
            fig2.add_trace(go.Scatter(
                x=xv, y=yv, mode='lines',
                name=f'{ser} (t\u1d5d fit)', showlegend=(row == 1),
                legendgroup=f'{ser}_hn', line=dict(**fit_style),
                hovertemplate=f'{ser}<br>Hours: %{{x:.0f}}<br>\u0394 Fit: %{{y:.2f}} ppm<extra></extra>',
            ), row=row, col=1)

for row in [1, 2]:
    fig2.add_vline(x=max_data_hours_300v, line_dash='dash', line_color='grey',
                   annotation_text='End of measured data',
                   annotation_position='top right', row=row, col=1)

fig2.update_layout(title='PXIe-4080 300V Gain Error - Offset-Normalised Drift (Post Jun 20)',
                   height=1000, hovermode='x unified',
                   legend=dict(x=1.02, y=1, bgcolor='rgba(255,255,255,0.7)'))
fig2.update_xaxes(title_text='Hours (linear)', row=1, col=1, range=[0, forecast_end_300v])
fig2.update_xaxes(title_text='Hours (log scale)', row=2, col=1,
                  type='log', range=[-2, np.log10(forecast_end_300v)])
fig2.update_yaxes(title_text='\u0394 Gain Error (ppm)', row=1, col=1)
fig2.update_yaxes(title_text='\u0394 Gain Error (ppm)', row=2, col=1)

# ── Combine figures and export ────────────────────────────────────────────────
div1 = fig1.to_html(full_html=False, include_plotlyjs=True,  div_id='plot_abs',
                    default_width='100%', default_height='700px', config={'responsive': True})
div2 = fig2.to_html(full_html=False, include_plotlyjs=False, div_id='plot_norm',
                    default_width='100%', default_height='700px', config={'responsive': True})

coeff_rows = ''
for ser in serials_300v:
    if ser not in norm_coeffs:
        continue
    A_f, beta_f, t_first, y_first = norm_coeffs[ser]
    coeff_rows += (f'<tr><td>{ser}</td><td>{A_f:.4f}</td>'
                   f'<td>{beta_f:.4f}</td><td>{y_first:.2f}</td></tr>\n')

html_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PXIe-4080 300V Drift Analysis</title>
  <style>
    body {{font-family: Arial, Helvetica, sans-serif; margin: 0; padding: 0; background: #f0f0f0;}}
    .plot-section {{background: #fff; margin: 14px 16px; padding: 14px 16px 8px;
                    border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.12);}}
    .plot-section h2 {{color: #1a1a1a; font-size: 16px; margin: 0 0 8px; font-weight: 600;}}
  </style>
</head>
<body>
  <div class="plot-section">
    <h2>Absolute Gain Error &#8212; 300V Range vs. Time (Post Jun 20)</h2>
    {div1}
  </div>
  <div class="plot-section">
    <h2>Offset-Normalised Gain Error &#8212; 300V Range (all serials start at 0 ppm)</h2>
    {div2}
  </div>

  <script>
  MathJax = {{ tex: {{ inlineMath: [['$','$']] }}, svg: {{ fontCache: 'global' }} }};
  </script>
  <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
  <div style="font-family:sans-serif;max-width:900px;margin:2em auto;padding:0 1em;">
    <h3 style="color:#4b0082;">Power-Law Drift Model (300V, fitted on t &ge; 50 h)</h3>
    <p>$$\\Delta E(t) = A\\,\\bigl(t^{{\\beta}} - t_{{\\text{{first}}}}^{{\\beta}}\\bigr)$$</p>
    <p style="font-size:0.85em;color:#333;line-height:1.6;">
      Fitted directly on zero-anchored (normalised) data so the least-squares
      residuals are minimised in the same space shown in Figure&nbsp;2.
      Physical basis: Fick&#8217;s second law gives moisture uptake in a thin
      film as $\\Delta M \\propto t^\\beta$, where $\\beta = 0.5$ for ideal
      Fickian diffusion and $\\beta &lt; 0.5$ for anomalous/hindered diffusion.
    </p>
    <p style="font-size:0.8em;color:#555;">$t$ = hours since window start &nbsp;|&nbsp;
      $t_{{\\text{{first}}}}$ = time of first measurement (anchors fit to zero) &nbsp;|&nbsp;
      Fitted on $t \\ge 50\\,\\text{{h}}$ &nbsp;|&nbsp; Forecast: 90 days</p>
    <h3 style="color:#4b0082;margin-top:2em;">Fitted Coefficients per Serial</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:0.85em;">
      <thead style="background:#4b0082;color:#fff;">
        <tr><th>Serial</th><th>A (ppm/h<sup>&beta;</sup>)</th><th>&beta; (diffusion exp.)</th><th>Baseline d (ppm)</th></tr>
      </thead>
      <tbody>{coeff_rows}</tbody>
    </table>
  </div>
</body>
</html>
"""

with open(OUTPUT_HTML_300V_DRIFT, 'w', encoding='utf-8') as fh:
    fh.write(html_page)

inject_branding_header(OUTPUT_HTML_300V_DRIFT, LOGO_BASE64)

print(f'\nWritten: {OUTPUT_HTML_300V_DRIFT}')
print(f'Measured span: {max_data_hours_300v:.1f} h  |  Forecast: {forecast_end_300v:.0f} h (~90 days)')
print(f'Power-law fit (2-param, normalised): {len(norm_coeffs)} serials')
print('NI/Emerson branding injected.')

