#!/usr/bin/env python3
"""
Tempo analysis for the cross-continental lullaby study (Experimental Data set).

Input : Tempo_Corrected.xlsx  (tabs "Tempo table" and "Corrected data")
Output: <OUT_DIR>/results.xlsx   one workbook, one tab per analysis
        <OUT_DIR>/report.txt     key numbers in plain sentences
        <OUT_DIR>/figures/       PNG (300 dpi) + PDF of every figure

Analysis plan
  1  Sample: participants and recordings per continent, demographics.
  2  Descriptives: BPM per song type and per continent x song type (values set by PRIMARY).
  3  Main model: linear mixed model, log2(BPM) ~ song type + (1 | participant).
     Song-type differences reported as % tempo difference with 95% CI.
  3b Random-slopes check: the same contrasts with an unstructured within-participant
     covariance of the song types (equivalent to random slopes for song type when each
     participant sang each song type at most once), and a test against model 3.
  4  Continent: song type x continent interaction (LRT), continent main effect
     (LRT), and lullaby-only tests across continents (ANOVA, Welch-type test,
     Kruskal-Wallis, Brown-Forsythe for spread).
  5  Model-free check: paired within-participant comparisons (paired t on
     log2 BPM and Wilcoxon), Holm-corrected, dz effect sizes.
  6  Covariates (exploratory): gender, age, children, musical training.
  8  Sensitivity: main model and paired tests on the other set of values (octave-corrected
     when PRIMARY = "ableton") and without the recordings flagged by the octave check.
Country-level comparisons are not run: most countries have too few participants.
Countries in EXCLUDE_COUNTRIES (default: Australia, 3 participants, which belongs to none of
the five sampled continents) are removed before all analyses.

Why log2(BPM): tempo differences are proportional (60 to 66 BPM is the same
step as 120 to 132), octave corrections are multiplicative, and the BPM
distribution is right-skewed. A model coefficient b on log2 BPM means the
tempo is (2**b - 1) * 100 % faster or slower. Set USE_LOG = False to model raw
BPM instead.

Mixed models are fitted with a built-in REML/ML random-intercept engine (numpy/scipy),
because statsmodels 0.15 failed on the ML fits. If statsmodels is installed, the main
model is re-fitted with statsmodels MixedLM as a cross-check and both are reported.

Run in the VS Code terminal:
    python -m pip install pandas numpy scipy statsmodels matplotlib openpyxl
    python tempo_analysis.py
"""

import os
import re
import sys
import warnings
import numpy as np
import pandas as pd
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, NullLocator, FuncFormatter

try:
    import statsmodels.formula.api as smf
    HAVE_SM = True
except ImportError:
    HAVE_SM = False

# =============================================================================
# CONFIG
# =============================================================================
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # folder containing 02_code
INPUT   = os.path.join(PROJECT, "03_output", "Tempo_Corrected.xlsx")
OUT_DIR = os.path.join(PROJECT, "03_output", "tempo_analysis_output")

USE_LOG = True              # model log2(BPM) (recommended) or raw BPM
# Which tempo values the main analysis uses:
#   "ableton"   = DAW values as analysed (metrical level set by tapping along in Ableton);
#                 the octave-corrected values are a sensitivity analysis   (paper default)
#   "corrected" = octave-corrected values as main analysis; DAW values as sensitivity
PRIMARY = "ableton"
REF_SONG = "Lullaby"        # reference level for song-type contrasts

# Australia is labelled "Asia " in the source sheet. Set the continent to use.
AUSTRALIA_CONTINENT = "Asia"      # "Asia" (as in source) or "Oceania"
# Countries excluded from all analyses. Australia (3 participants) is excluded because
# it belongs to none of the five sampled continents.
EXCLUDE_COUNTRIES = ["Australia"]

# Musical training: many participants left this blank. Decide what blank means.
TRAINING_BLANK_AS = None          # None = missing (dropped in covariate model)
                                  # or "None" = treat blank as no training

# Age 61-99 has only 8 participants; merge it into 41-60 for the covariate model?
MERGE_OLDEST_AGE = True

MAKE_COUNTRY_FIGURE = False # per-country lullaby plot; off because most countries have too few participants
MIN_COUNTRY_N = 3           # countries with fewer lullabies are left out of the country figure
SEED = 1
# =============================================================================

SONGS = ["Lullaby", "Love song", "Sleep song"]
MAIN_LABEL = "Ableton" if PRIMARY == "ableton" else "corrected"
ALT_LABEL = "octave-corrected" if PRIMARY == "ableton" else "uncorrected"
FLAG_LABEL = "without recordings flagged by the octave check"
COLORS = {"Lullaby": "#2a78d6", "Love song": "#eb6834", "Sleep song": "#1baf7a"}  # validated, colour-blind safe
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

warnings.filterwarnings("ignore", category=FutureWarning)
os.makedirs(os.path.join(OUT_DIR, "figures"), exist_ok=True)
REPORT = []
TABLES = {}


def say(line=""):
    print(line)
    REPORT.append(line)


def pct(b):
    """log2 coefficient -> % tempo difference."""
    return (2.0 ** b - 1.0) * 100.0


# =============================================================================
# 1  LOAD AND CLEAN
# =============================================================================
def clean_country(s):
    s = str(s).strip()
    fix = {"german": "Germany", "india": "India", "south africa": "South Africa",
           "united kingdom": "United Kingdom", "usa": "USA", "kirgisistan": "Kyrgyzstan"}
    return fix.get(s.lower(), s[:1].upper() + s[1:])


def clean_gender(s):
    s = str(s).strip().lower()
    return {"female": "Female", "frau": "Female", "male": "Male"}.get(s, np.nan)


def clean_training(s):
    if pd.isna(s) or str(s).strip() == "":
        return TRAINING_BLANK_AS if TRAINING_BLANK_AS is not None else np.nan
    s = str(s).replace("\xa0", " ").strip().lower()
    if s in ("no", "none"):
        return "None"
    if "less than 5" in s or "menos de 5" in s or "weniger als 5" in s:
        return "<5 years"
    if "5-10" in s or "5 - 10" in s or "zwischen" in s or "entre" in s:
        return "5-10 years"
    if "more than 10" in s or "mehr als 10" in s or "más de 10" in s or "mas de 10" in s:
        return ">10 years"
    return np.nan


def load():
    if not os.path.exists(INPUT):
        sys.exit(f"Input not found: {INPUT}")
    tt = pd.read_excel(INPUT, sheet_name="Tempo table", header=3)
    tt = tt[pd.to_numeric(tt["ID"], errors="coerce").notna()].copy()
    tt["ID"] = tt["ID"].astype(int)
    cd = pd.read_excel(INPUT, sheet_name="Corrected data", dtype=str)
    cd["row"] = cd["row"].astype(int)
    demo = cd.set_index("row")[["Continent", "Country of origin", "What is your gender?",
                                "How old are you?", "Do you have children?",
                                "Have you had any formal musical training?", "Language"]]

    d = tt.rename(columns={"ID": "pid", "Song type": "song_type", "Analysed BPM": "bpm_raw",
                           "Tapped BPM": "bpm_tap", "Corrected BPM": "bpm",
                           "Correction": "correction", "Status": "status"})
    d = d[["pid", "song_type", "bpm_raw", "bpm_tap", "bpm", "correction", "status"]]
    d = d.join(demo, on="pid")
    for c in ("bpm_raw", "bpm_tap", "bpm"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["correction"] = d["correction"].fillna("").astype(str).replace("nan", "")

    d["continent"] = d["Continent"].astype(str).str.strip()
    d["country"] = d["Country of origin"].map(clean_country)
    d.loc[d["country"] == "Australia", "continent"] = AUSTRALIA_CONTINENT
    d["gender"] = d["What is your gender?"].map(clean_gender)
    age = d["How old are you?"].astype(str).str.strip()
    if MERGE_OLDEST_AGE:
        age = age.replace({"41-60": "41+", "61-99": "41+"})
    d["age"] = age.where(age.isin(["18-24", "25-40", "41-60", "61-99", "41+"]))
    d["children"] = d["Do you have children?"].astype(str).str.strip().where(
        lambda s: s.isin(["Yes", "No"]))
    d["training"] = d["Have you had any formal musical training?"].map(clean_training)

    n_all = len(d)
    excl_c = d["country"].isin(EXCLUDE_COUNTRIES)
    if excl_c.any():
        say(f"Excluded countries {', '.join(EXCLUDE_COUNTRIES)}: {d.loc[excl_c, 'pid'].nunique()} participants, "
            f"{int(excl_c.sum())} recordings.")
    d = d[~excl_c].copy()
    excluded = d[d["status"] != "Included"]
    d = d[(d["status"] == "Included") & d["bpm"].notna() & (d["continent"] != "X")].copy()
    d["song_type"] = pd.Categorical(d["song_type"], SONGS)
    d["bpm_corr"] = d["bpm"]
    if PRIMARY == "ableton":
        d["bpm"], d["bpm_alt"] = d["bpm_raw"], d["bpm_corr"]
    else:
        d["bpm"], d["bpm_alt"] = d["bpm_corr"], d["bpm_raw"]
    if d["bpm"].isna().any():
        sys.exit("Missing tempo values among included recordings: " + ", ".join(map(str, d.loc[d.bpm.isna(), "pid"])))
    d["y"] = np.log2(d["bpm"]) if USE_LOG else d["bpm"]
    d["y_alt"] = np.log2(d["bpm_alt"]) if USE_LOG else d["bpm_alt"]
    d["corrected"] = d["correction"].isin(["halved", "doubled"])
    say(f"Loaded {n_all} recordings; {len(excluded)} excluded (skipped during tapping); "
        f"{len(d)} analysed from {d['pid'].nunique()} participants.")
    return d


# =============================================================================
# helpers
# =============================================================================
def describe(x):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    n = len(x)
    lg = np.log2(x)
    se = lg.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    tcrit = stats.t.ppf(0.975, n - 1) if n > 1 else np.nan
    return pd.Series({
        "n": n, "mean_bpm": x.mean(), "sd_bpm": x.std(ddof=1) if n > 1 else np.nan,
        "median_bpm": np.median(x), "q1": np.percentile(x, 25), "q3": np.percentile(x, 75),
        "min": x.min(), "max": x.max(),
        "geo_mean_bpm": 2 ** lg.mean(),
        "geo_ci_low": 2 ** (lg.mean() - tcrit * se) if n > 1 else np.nan,
        "geo_ci_high": 2 ** (lg.mean() + tcrit * se) if n > 1 else np.nan,
        "cv_pct": x.std(ddof=1) / x.mean() * 100 if n > 1 else np.nan,
    })


def holm(p):
    p = np.asarray(p, float)
    order = np.argsort(p)
    m = len(p)
    adj = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * p[i])
        adj[i] = min(1.0, running)
    return adj


# =============================================================================
# LINEAR MIXED MODEL ENGINE (random intercept per participant)
# =============================================================================
# y = X b + u_participant + e,  u ~ N(0, s2_u),  e ~ N(0, s2_e).
# With lam = s2_u / s2_e, V_i^-1 = (I - c_i J) / s2_e with c_i = lam / (1 + n_i lam),
# so GLS and the (RE)ML likelihood have closed forms per participant. lam is found by
# one-dimensional optimisation; b and s2_e are profiled out. This is the same model
# that lme4::lmer(y ~ X + (1 | participant)) and statsmodels MixedLM fit.
REFS = {"song_type": None, "continent": None, "gender": "Female", "age": "25-40",
        "children": "No", "training": None}


class LMMFit:
    pass


def lmm_fit(y, X, groups, names, reml=True):
    y = np.asarray(y, float)
    X = np.asarray(X, float)
    N, p = X.shape
    codes, _ = pd.factorize(np.asarray(groups))
    G = codes.max() + 1
    n_i = np.bincount(codes, minlength=G).astype(float)
    Sx = np.zeros((G, p)); np.add.at(Sx, codes, X)
    Sy = np.zeros(G); np.add.at(Sy, codes, y)
    XtX, Xty, yty = X.T @ X, X.T @ y, y @ y

    def parts(lam):
        c = lam / (1.0 + n_i * lam)
        XWX = XtX - (Sx.T * c) @ Sx
        XWy = Xty - (Sx.T * c) @ Sy
        yWy = yty - (c * Sy ** 2).sum()
        beta = np.linalg.solve(XWX, XWy)
        rss = yWy - XWy @ beta
        return beta, rss, XWX, np.log1p(n_i * lam).sum()

    def m2ll(t):
        beta, rss, XWX, ld = parts(np.exp(t))
        if reml:
            s2 = rss / (N - p)
            ldx = np.linalg.slogdet(XWX)[1]
            return (N - p) * np.log(2 * np.pi * s2) + ld + ldx + (N - p)
        s2 = rss / N
        return N * np.log(2 * np.pi * s2) + ld + N

    from scipy.optimize import minimize_scalar
    grid = np.linspace(-12, 6, 37)
    t0 = grid[np.argmin([m2ll(t) for t in grid])]
    res = minimize_scalar(m2ll, bounds=(max(-14, t0 - 1), min(8, t0 + 1)), method="bounded")
    t = res.x if res.fun <= m2ll(t0) else t0
    lam = np.exp(t)
    beta, rss, XWX, _ = parts(lam)
    s2 = rss / (N - p) if reml else rss / N
    f = LMMFit()
    f.names = list(names)
    f.beta = pd.Series(beta, index=names)
    f.cov = pd.DataFrame(s2 * np.linalg.inv(XWX), index=names, columns=names)
    f.se = pd.Series(np.sqrt(np.diag(f.cov)), index=names)
    f.s2_e, f.s2_u = s2, s2 * lam
    f.icc = f.s2_u / (f.s2_u + f.s2_e)
    f.llf = -0.5 * m2ll(t)
    f.n_obs, f.n_groups, f.reml = N, G, reml
    f.boundary = lam < 1e-5
    return f


def design(d, terms):
    """Treatment-coded design matrix. terms: column names or (a, b) tuples for interactions."""
    cols = {"Intercept": np.ones(len(d))}
    dummies = {}
    for v in {x for t in terms for x in (t if isinstance(t, tuple) else (t,))}:
        lv = list(d[v].cat.categories) if hasattr(d[v], "cat") else sorted(d[v].dropna().unique())
        lv = [l for l in lv if l in set(d[v])]
        ref = REFS.get(v) or (REF_SONG if v == "song_type" else lv[0])
        dummies[v] = {f"{v}[{l}]": (d[v] == l).astype(float).values for l in lv if l != ref}
    for t in terms:
        if isinstance(t, tuple):
            a, b = t
            for na, xa in dummies[a].items():
                for nb, xb in dummies[b].items():
                    x = xa * xb
                    if x.sum() > 0:
                        cols[f"{na}:{nb}"] = x
        else:
            cols.update(dummies[t])
    X = pd.DataFrame(cols, index=d.index)
    return X.values, list(X.columns)


def fit_terms(d, ycol, terms, reml=True):
    X, names = design(d, terms)
    return lmm_fit(d[ycol].values, X, d["pid"].values, names, reml=reml)


def lrt(full, reduced):
    stat = max(0.0, 2 * (full.llf - reduced.llf))
    df = len(full.names) - len(reduced.names)
    return stat, df, stats.chi2.sf(stat, df)


def fe_table(fit, label):
    z = fit.beta / fit.se
    t = pd.DataFrame({"model": label, "term": fit.names, "estimate": fit.beta.values, "se": fit.se.values,
                      "ci_low": (fit.beta - 1.96 * fit.se).values, "ci_high": (fit.beta + 1.96 * fit.se).values,
                      "z": z.values, "p": 2 * stats.norm.sf(np.abs(z.values))})
    if USE_LOG:
        t["pct_diff"] = pct(t["estimate"])
        t["pct_ci_low"] = pct(t["ci_low"])
        t["pct_ci_high"] = pct(t["ci_high"])
    t["participant_var"] = fit.s2_u
    t["residual_var"] = fit.s2_e
    return t


def contrast(fit, a, b):
    """Estimate of level a minus level b of song_type (names as in design)."""
    w = pd.Series(0.0, index=fit.names)
    for lvl, sign in ((a, 1), (b, -1)):
        nm = f"song_type[{lvl}]"
        if nm in w.index:
            w[nm] += sign
    est = float(w @ fit.beta)
    se = float(np.sqrt(w @ fit.cov.values @ w))
    z = est / se
    return est, se, 2 * stats.norm.sf(abs(z))


# =============================================================================
# 2  SAMPLE + DESCRIPTIVES
# =============================================================================
def sample_and_descriptives(d):
    say("\n== 1 Sample ==")
    p = d.drop_duplicates("pid")
    samp = (d.groupby("continent").agg(participants=("pid", "nunique"), recordings=("bpm", "size"),
                                       countries=("country", "nunique"), corrected=("corrected", "sum")))
    TABLES["Sample"] = samp.reset_index()
    for c, r in samp.iterrows():
        say(f"  {c}: {r.participants} participants, {r.countries} countries, {r.recordings} recordings")
    demo = []
    for col in ("gender", "age", "children", "training"):
        vc = p[col].value_counts(dropna=False)
        for k, v in vc.items():
            demo.append({"variable": col, "level": "missing" if pd.isna(k) else k, "participants": v})
    TABLES["Demographics"] = pd.DataFrame(demo)
    rec = d.groupby("song_type", observed=True).agg(recordings=("bpm", "size"), corrected=("corrected", "sum"))
    say("  Recordings per song type: " + ", ".join(f"{k} {v.recordings} ({v.corrected} octave-corrected)"
                                                  for k, v in rec.iterrows()))

    say(f"\n== 2 Descriptives ({MAIN_LABEL} BPM) ==")
    ds = d.groupby("song_type", observed=True)["bpm"].apply(describe).unstack()
    TABLES["Descriptives"] = ds.reset_index()
    for k, r in ds.iterrows():
        say(f"  {k}: median {r.median_bpm:.1f} BPM (IQR {r.q1:.1f}-{r.q3:.1f}), "
            f"geometric mean {r.geo_mean_bpm:.1f} [{r.geo_ci_low:.1f}, {r.geo_ci_high:.1f}], n = {int(r.n)}")
    dc = d.groupby(["song_type", "continent"], observed=True)["bpm"].apply(describe).unstack()
    TABLES["Descriptives continent"] = dc.reset_index()


# =============================================================================
# 3-4  MIXED MODELS
# =============================================================================
def models(d, ycol="y", label=None):
    label = label or MAIN_LABEL
    out = {}
    m0 = fit_terms(d, ycol, [], reml=False)
    m1_ml = fit_terms(d, ycol, ["song_type"], reml=False)
    m1 = fit_terms(d, ycol, ["song_type"], reml=True)
    out["song_lrt"] = lrt(m1_ml, m0)
    out["icc"] = m1.icc
    out["boundary"] = m1.boundary
    rows = []
    for a, b in [("Love song", "Lullaby"), ("Sleep song", "Lullaby"), ("Love song", "Sleep song")]:
        est, se, p = contrast(m1, a, b)
        r = {"analysis": label, "contrast": f"{a} - {b}", "estimate": est, "se": se,
             "ci_low": est - 1.96 * se, "ci_high": est + 1.96 * se, "p": p}
        if USE_LOG:
            r.update(pct_diff=pct(est), pct_ci_low=pct(est - 1.96 * se), pct_ci_high=pct(est + 1.96 * se))
        rows.append(r)
    c = pd.DataFrame(rows)
    c["p_holm"] = holm(c["p"])
    out["contrasts"] = c
    out["m1"] = fe_table(m1, f"M1 song type ({label})")

    m2_ml = fit_terms(d, ycol, ["song_type", "continent"], reml=False)
    m3_ml = fit_terms(d, ycol, ["song_type", "continent", ("song_type", "continent")], reml=False)
    out["continent_lrt"] = lrt(m2_ml, m1_ml)
    out["interaction_lrt"] = lrt(m3_ml, m2_ml)
    m3 = fit_terms(d, ycol, ["song_type", "continent", ("song_type", "continent")], reml=True)
    out["m3"] = fe_table(m3, f"M3 song type x continent ({label})")
    out["n"] = (m1.n_obs, m1.n_groups)
    return out


def report_models(o, label):
    s, df, p = o["song_lrt"]
    say(f"  [{label}] {o['n'][0]} recordings, {o['n'][1]} participants. Song type effect: "
        f"LRT chi2({df}) = {s:.2f}, p = {p:.3g}; participant ICC = {o['icc']:.2f}"
        + (" (participant variance at zero)" if o["boundary"] else ""))
    for _, r in o["contrasts"].iterrows():
        if USE_LOG:
            say(f"    {r.contrast}: {r.pct_diff:+.1f}% [{r.pct_ci_low:+.1f}, {r.pct_ci_high:+.1f}], "
                f"p = {r.p:.3g}, Holm p = {r.p_holm:.3g}")
        else:
            say(f"    {r.contrast}: {r.estimate:+.1f} BPM [{r.ci_low:+.1f}, {r.ci_high:+.1f}], "
                f"p = {r.p:.3g}, Holm p = {r.p_holm:.3g}")
    s, df, p = o["continent_lrt"]
    say(f"  [{label}] Continent main effect: LRT chi2({df}) = {s:.2f}, p = {p:.3g}")
    s, df, p = o["interaction_lrt"]
    say(f"  [{label}] Song type x continent: LRT chi2({df}) = {s:.2f}, p = {p:.3g}")


def unstructured_check(d, ycol="y", label=None):
    label = label or MAIN_LABEL
    """Random-slopes check. Each participant sang each song type at most once, so a model with a
    random intercept plus random song-type slopes is equivalent to letting the three song types have
    their own variances and correlations within a participant (unstructured covariance). Fixed effects
    are estimated by GLS; the covariance is estimated by (RE)ML."""
    from scipy.optimize import minimize
    levels = list(d["song_type"].cat.categories)
    k = len(levels)
    if d.groupby(["pid", "song_type"], observed=True).size().max() > 1:
        say("  unstructured check skipped: some participants have repeated recordings of one song type")
        return None
    X_all, names = design(d, ["song_type"])
    groups = []
    for _, idx in d.groupby("pid").indices.items():
        g = d.iloc[idx]
        groups.append((np.array([levels.index(s) for s in g["song_type"].astype(str)]),
                       X_all[idx], g[ycol].values))
    tri = np.tril_indices(k)

    def V_of(th):
        L = np.zeros((k, k)); L[tri] = th
        L[np.diag_indices(k)] = np.exp(np.diag(L))
        return L @ L.T

    def fit(Xcols, reml):
        def m2ll(th, keep=False):
            V = V_of(th)
            XtVX = 0; XtVy = 0; pieces = []
            for li, X, y in groups:
                Vi = V[np.ix_(li, li)]
                Vinv = np.linalg.inv(Vi)
                Xs = X[:, Xcols]
                XtVX = XtVX + Xs.T @ Vinv @ Xs
                XtVy = XtVy + Xs.T @ Vinv @ y
                pieces.append((Vi, Vinv, Xs, y))
            b = np.linalg.solve(XtVX, XtVy)
            out = 0.0
            for Vi, Vinv, Xs, y in pieces:
                r = y - Xs @ b
                out += np.linalg.slogdet(Vi)[1] + r @ Vinv @ r + len(y) * np.log(2 * np.pi)
            if reml:
                out += np.linalg.slogdet(XtVX)[1]
            if keep:
                return out, b, np.linalg.inv(XtVX)
            return out
        th0 = np.zeros(len(tri[0])); th0[[i for i, (a, c) in enumerate(zip(*tri)) if a == c]] = np.log(d[ycol].std())
        r = minimize(m2ll, th0, method="Nelder-Mead", options=dict(maxiter=40000, maxfev=40000, xatol=1e-9, fatol=1e-11))
        r = minimize(m2ll, r.x, method="BFGS")
        val, b, cov = m2ll(r.x, keep=True)
        return -0.5 * val, b, cov, V_of(r.x)

    allc = list(range(len(names)))
    ll_reml, b, cov, V = fit(allc, True)
    ll_ml = fit(allc, False)[0]
    ll0_ml = fit([0], False)[0]
    stat = 2 * (ll_ml - ll0_ml); df = len(names) - 1
    cs = fit_terms(d, ycol, ["song_type"], reml=True)
    st_cs = max(0.0, 2 * (ll_reml - cs.llf)); df_cs = k * (k + 1) // 2 - 2
    beta = pd.Series(b, index=names); C = pd.DataFrame(cov, index=names, columns=names)
    say(f"  [{label}] song type effect: LRT chi2({df}) = {stat:.2f}, p = {stats.chi2.sf(stat, df):.3g}; "
        f"unstructured vs random intercept only: chi2({df_cs}) = {st_cs:.2f}, p = {stats.chi2.sf(st_cs, df_cs):.3g}")
    rows = []
    for a, bb in [("Love song", "Lullaby"), ("Sleep song", "Lullaby"), ("Love song", "Sleep song")]:
        w = pd.Series(0.0, index=names)
        for lvl, sign in ((a, 1), (bb, -1)):
            if f"song_type[{lvl}]" in w.index:
                w[f"song_type[{lvl}]"] += sign
        est = float(w @ beta); se = float(np.sqrt(w @ C.values @ w)); p = 2 * stats.norm.sf(abs(est / se))
        rows.append({"analysis": f"unstructured ({label})", "contrast": f"{a} - {bb}", "estimate": est, "se": se,
                     "ci_low": est - 1.96 * se, "ci_high": est + 1.96 * se, "p": p,
                     "pct_diff": pct(est), "pct_ci_low": pct(est - 1.96 * se), "pct_ci_high": pct(est + 1.96 * se)})
    c = pd.DataFrame(rows); c["p_holm"] = holm(c["p"])
    for _, r in c.iterrows():
        say(f"    {r.contrast}: {r.pct_diff:+.1f}% [{r.pct_ci_low:+.1f}, {r.pct_ci_high:+.1f}], "
            f"p = {r.p:.3g}, Holm p = {r.p_holm:.3g}")
    say("    within-participant covariance (song types " + ", ".join(levels) + "): "
        + "; ".join(" ".join(f"{v:.4f}" for v in row) for row in V))
    return c


def statsmodels_check(d):
    """Cross-check of M1 against statsmodels MixedLM (REML). Runs only if statsmodels is installed."""
    if not HAVE_SM:
        return
    say("\n== Cross-check: M1 in statsmodels MixedLM (REML) ==")
    try:
        dd = d.copy()
        dd["song"] = dd["song_type"].astype(str)
        sm = smf.mixedlm(f"y ~ C(song, Treatment('{REF_SONG}'))", dd, groups=dd["pid"]).fit(reml=True)
        own = fit_terms(d, "y", ["song_type"], reml=True)
        for nm in own.names[1:]:
            lvl = nm.split("[")[1].rstrip("]")
            key = [k for k in sm.fe_params.index if lvl in k][0]
            say(f"  {lvl} vs {REF_SONG}: built-in {own.beta[nm]:.4f} (SE {own.se[nm]:.4f}), "
                f"statsmodels {sm.fe_params[key]:.4f} (SE {sm.bse_fe[key]:.4f})")
        say(f"  participant variance: built-in {own.s2_u:.4f}, statsmodels {sm.cov_re.iloc[0, 0]:.4f}; "
            f"residual: built-in {own.s2_e:.4f}, statsmodels {sm.scale:.4f}")
    except Exception as e:
        say(f"  statsmodels cross-check failed ({type(e).__name__}: {e}); built-in results stand.")


# =============================================================================
# 4b  LULLABY ACROSS CONTINENTS (model-free)
# =============================================================================
def lullaby_continents(d):
    say("\n== 4b Lullaby tempo across continents ==")
    rows = []
    for song in SONGS:
        s = d[d.song_type == song]
        groups = [g["y"].values for _, g in s.groupby("continent") if len(g) >= 2]
        names = [c for c, g in s.groupby("continent") if len(g) >= 2]
        F, pF = stats.f_oneway(*groups)
        ag = stats.alexandergovern(*groups)
        H, pH = stats.kruskal(*groups)
        bf, pbf = stats.levene(*groups, center="median")
        N, k = sum(map(len, groups)), len(groups)
        grand = np.concatenate(groups).mean()
        ss_b = sum(len(g) * (g.mean() - grand) ** 2 for g in groups)
        ss_t = ((np.concatenate(groups) - grand) ** 2).sum()
        rows.append({"song_type": song, "continents": ", ".join(names), "N": N,
                     "anova_F": F, "anova_p": pF, "eta_sq": ss_b / ss_t,
                     "welch_type_A": ag.statistic, "welch_type_p": ag.pvalue,
                     "kruskal_H": H, "kruskal_p": pH, "epsilon_sq": H * (N + 1) / (N ** 2 - 1),
                     "brown_forsythe_W": bf, "brown_forsythe_p": pbf})
    t = pd.DataFrame(rows)
    TABLES["Continent tests"] = t
    for _, r in t.iterrows():
        say(f"  {r.song_type}: ANOVA F = {r.anova_F:.2f}, p = {r.anova_p:.3g}, eta2 = {r.eta_sq:.3f}; "
            f"Kruskal-Wallis H = {r.kruskal_H:.2f}, p = {r.kruskal_p:.3g}; "
            f"spread (Brown-Forsythe) p = {r.brown_forsythe_p:.3g}")


# =============================================================================
# 5  PAIRED WITHIN-PARTICIPANT COMPARISONS
# =============================================================================
def paired(d, ycol="y", bpmcol="bpm", label=None):
    label = label or MAIN_LABEL
    w = d.pivot_table(index="pid", columns="song_type", values=ycol, observed=True)
    wb = d.pivot_table(index="pid", columns="song_type", values=bpmcol, observed=True)
    rows = []
    for a, b in [("Love song", "Lullaby"), ("Sleep song", "Lullaby"), ("Love song", "Sleep song")]:
        both = w[[a, b]].dropna()
        diff = both[a] - both[b]
        t, pt = stats.ttest_rel(both[a], both[b])
        wil = stats.wilcoxon(both[a], both[b])
        bpm_diff = (wb.loc[both.index, a] - wb.loc[both.index, b])
        rows.append({"analysis": label, "comparison": f"{a} - {b}", "n_pairs": len(both),
                     "mean_diff_log2" if USE_LOG else "mean_diff": diff.mean(),
                     "pct_diff_geo": pct(diff.mean()) if USE_LOG else np.nan,
                     "median_diff_bpm": bpm_diff.median(), "dz": diff.mean() / diff.std(ddof=1),
                     "t": t, "p_t": pt, "wilcoxon_W": wil.statistic, "p_wilcoxon": wil.pvalue,
                     "share_faster_pct": (diff > 0).mean() * 100})
    t = pd.DataFrame(rows)
    t["p_t_holm"] = holm(t["p_t"])
    t["p_wilcoxon_holm"] = holm(t["p_wilcoxon"])
    return t


def report_paired(t):
    for _, r in t.iterrows():
        extra = f"{r.pct_diff_geo:+.1f}% (geometric), " if USE_LOG else ""
        say(f"  [{r.analysis}] {r.comparison}: {extra}median {r.median_diff_bpm:+.1f} BPM, dz = {r.dz:.2f}, "
            f"n = {r.n_pairs}, p(t, Holm) = {r.p_t_holm:.3g}, p(Wilcoxon, Holm) = {r.p_wilcoxon_holm:.3g}; "
            f"{r.share_faster_pct:.0f}% of participants faster in the first")


# =============================================================================
# 6  COVARIATES (exploratory)
# =============================================================================
def covariates(d):
    say("\n== 6 Covariates (exploratory, added to the song-type model) ==")
    covs = ["gender", "age", "children", "training"]
    dd = d.dropna(subset=covs).copy()
    say(f"  Complete covariate data: {dd['pid'].nunique()} participants, {len(dd)} recordings "
        f"(training blank treated as {'missing' if TRAINING_BLANK_AS is None else TRAINING_BLANK_AS}).")
    full_ml = fit_terms(dd, "y", ["song_type"] + covs, reml=False)
    rows = []
    for c in covs:
        red_ml = fit_terms(dd, "y", ["song_type"] + [x for x in covs if x != c], reml=False)
        s, df, p = lrt(full_ml, red_ml)
        rows.append({"covariate": c, "levels": ", ".join(sorted(dd[c].unique())), "lrt_chi2": s, "df": df, "p": p})
    lr = pd.DataFrame(rows)
    lr["p_holm"] = holm(lr["p"])
    for _, r in lr.iterrows():
        say(f"  {r.covariate}: LRT chi2({r.df}) = {r.lrt_chi2:.2f}, p = {r.p:.3g}, Holm p = {r.p_holm:.3g}")
    TABLES["Covariates LRT"] = lr
    TABLES["Covariates model"] = fe_table(fit_terms(dd, "y", ["song_type"] + covs, reml=True), "M4 covariates")


# =============================================================================
# FIGURES
# =============================================================================
def style():
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 9, "axes.edgecolor": INK2, "axes.linewidth": 0.6, "axes.labelcolor": INK,
        "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
        "legend.frameon": False, "savefig.dpi": 300, "savefig.bbox": "tight", "pdf.fonttype": 42,
    })


def log_bpm_axis(ax, lo=35, hi=170, axis="y", ticks=(40, 50, 60, 70, 80, 100, 120, 140, 160)):
    ticks = [t for t in ticks if lo <= t <= hi]
    a = ax.yaxis if axis == "y" else ax.xaxis
    (ax.set_yscale if axis == "y" else ax.set_xscale)("log", base=2)
    a.set_major_locator(FixedLocator(ticks))
    a.set_minor_locator(NullLocator())
    a.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}"))
    (ax.set_ylim if axis == "y" else ax.set_xlim)(lo, hi)


def save(fig, name):
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(OUT_DIR, "figures", f"{name}.{ext}"))
    plt.close(fig)


def fig_song_types(d):
    rng = np.random.default_rng(SEED)
    fig, ax = plt.subplots(figsize=(4.2, 3.6))
    for i, s in enumerate(SONGS):
        v = d.loc[d.song_type == s, "bpm"].values
        x = i + rng.uniform(-0.18, 0.18, len(v))
        ax.scatter(x, v, s=9, color=COLORS[s], alpha=0.45, linewidths=0, zorder=2)
        q1, med, q3 = np.percentile(v, [25, 50, 75])
        ax.plot([i + 0.27, i + 0.27], [q1, q3], color=INK2, lw=2, solid_capstyle="round", zorder=3)
        ax.plot(i + 0.27, med, "o", ms=6, mfc="white", mec=INK, mew=1.2, zorder=4)
        ax.text(i + 0.36, med, f"{med:.0f}", va="center", fontsize=8, color=INK)
    ax.set_xticks(range(3), SONGS)
    ax.grid(axis="x", visible=False)
    log_bpm_axis(ax)
    ax.set_ylabel("Tempo (BPM, log scale)")
    ax.set_title("Tempo by song type", loc="left", fontsize=10, color=INK)
    ax.text(0, -0.17, "Dots: recordings. Bar: interquartile range. Circle and number: median.",
            transform=ax.transAxes, fontsize=7, color=INK2)
    save(fig, "fig1_tempo_by_song_type")


def fig_paired(d):
    w = d.pivot_table(index="pid", columns="song_type", values="bpm", observed=True)
    rng = np.random.default_rng(SEED)
    comps = [("Love song", "Lullaby"), ("Sleep song", "Lullaby")]
    fig, ax = plt.subplots(figsize=(4.0, 3.4))
    for i, (a, b) in enumerate(comps):
        both = w[[a, b]].dropna()
        r = (both[a] / both[b] - 1) * 100
        x = i + rng.uniform(-0.18, 0.18, len(r))
        ax.scatter(x, r, s=9, color=COLORS[a], alpha=0.5, linewidths=0, zorder=2)
        med = np.median(r)
        ax.plot([i - 0.25, i + 0.25], [med, med], color=INK, lw=2, solid_capstyle="round", zorder=3)
        ax.text(i + 0.3, med, f"{med:+.0f}%", va="center", fontsize=8, color=INK)
    ax.axhline(0, color=INK2, lw=0.8, zorder=1)
    ax.set_xticks(range(2), [f"{a}\nvs lullaby" for a, _ in comps])
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("Tempo difference within participant (%)")
    ax.set_title("Same singer, different song", loc="left", fontsize=10, color=INK)
    ax.text(0, -0.2, "Dots: participants. Line and number: median difference.", transform=ax.transAxes,
            fontsize=7, color=INK2)
    save(fig, "fig2_within_participant_differences")


def fig_continents(d):
    conts = sorted(d["continent"].unique())
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 3.2), sharey=True)
    for ax, s in zip(axes, SONGS):
        sub = d[d.song_type == s]
        overall = describe(sub["bpm"].values).geo_mean_bpm
        ax.axhline(overall, color=COLORS[s], lw=1, ls="--", alpha=0.8, zorder=1)
        ax.text(0.03, 0.96, f"- - mean all continents: {overall:.1f} BPM", transform=ax.transAxes,
                ha="left", va="top", fontsize=7, color=INK2)
        for j, c in enumerate(conts):
            v = sub.loc[sub.continent == c, "bpm"].values
            if len(v) < 2:
                continue
            ds = describe(v)
            ax.plot([j, j], [ds.geo_ci_low, ds.geo_ci_high], color=COLORS[s], lw=2, solid_capstyle="round")
            ax.plot(j, ds.geo_mean_bpm, "o", ms=6, color=COLORS[s], mec="white", mew=1)
            ax.text(j, ds.geo_ci_low / 1.04, f"n={len(v)}", ha="center", va="top", fontsize=6.5, color=INK2)
        short = {"North America": "N. America", "South America": "S. America"}
        ax.set_xticks(range(len(conts)), [short.get(c, c) for c in conts], fontsize=7.5, rotation=35, ha="right")
        ax.grid(axis="x", visible=False)
        ax.set_title(s, loc="left", fontsize=9.5, color=INK)
        log_bpm_axis(ax, 45, 120)
    axes[0].set_ylabel("Tempo (BPM, log scale)")
    fig.suptitle("Geometric mean tempo with 95% CI by continent", x=0.01, ha="left", fontsize=10, color=INK)
    fig.tight_layout()
    save(fig, "fig3_continent_by_song_type")


def fig_countries(d):
    s = d[d.song_type == "Lullaby"]
    g = s.groupby("country")["bpm"].agg(["median", "size"])
    g = g[g["size"] >= MIN_COUNTRY_N].sort_values("median")
    cont = s.groupby("country")["continent"].first()
    fig, ax = plt.subplots(figsize=(4.4, 0.22 * len(g) + 1.0))
    rng = np.random.default_rng(SEED)
    for i, (c, r) in enumerate(g.iterrows()):
        v = s.loc[s.country == c, "bpm"].values
        ax.scatter(v, i + rng.uniform(-0.15, 0.15, len(v)), s=8, color=COLORS["Lullaby"], alpha=0.45, linewidths=0)
        ax.plot(r["median"], i, "|", ms=10, mew=2, color=INK)
    ax.set_yticks(range(len(g)), [f"{c} ({cont[c]}, n={int(r['size'])})" for c, r in g.iterrows()], fontsize=7)
    ax.grid(axis="y", visible=False)
    log_bpm_axis(ax, 38, 140, axis="x")
    ax.axvline(s["bpm"].median(), color=INK2, lw=0.8, ls="--")
    ax.set_xlabel("Lullaby tempo (BPM, log scale); bar = country median, dashed = overall median")
    ax.set_title(f"Lullaby tempo by country (n >= {MIN_COUNTRY_N})", loc="left", fontsize=10, color=INK)
    save(fig, "fig4_lullaby_by_country")


def fig_corrections(d):
    s = d[d["bpm_tap"].notna()]
    fig, ax = plt.subplots(figsize=(4.0, 3.8))
    lo, hi = 35, 200
    xs = np.array([lo, hi])
    for f, lab in [(1, "1:1"), (2, "2:1"), (0.5, "1:2")]:
        ax.plot(xs, xs * f, color=INK2 if f == 1 else GRID, lw=0.9 if f == 1 else 1.2, zorder=1)
        xe = hi / max(f, 1) / 1.08
        ax.text(xe, xe * f, lab, fontsize=7, color=INK2, ha="right", va="bottom")
    keep = s[~s.corrected]
    fix = s[s.corrected]
    ax.scatter(keep.bpm_tap, keep.bpm_raw, s=10, color="#9b9a95", alpha=0.6, linewidths=0, label="Unchanged", zorder=2)
    ax.scatter(fix.bpm_tap, fix.bpm_raw, s=16, facecolors="none", edgecolors=COLORS["Love song"], lw=1,
               label="Before correction", zorder=3)
    ax.scatter(fix.bpm_tap, fix.bpm_corr, s=16, color=COLORS["Love song"], linewidths=0, label="After correction", zorder=4)
    for _, r in fix.iterrows():
        ax.plot([r.bpm_tap, r.bpm_tap], [r.bpm_raw, r.bpm_corr], color=COLORS["Love song"], lw=0.5, alpha=0.6, zorder=2)
    log_bpm_axis(ax, lo, hi, ticks=(40, 50, 60, 80, 100, 120, 160))
    log_bpm_axis(ax, lo, hi, axis="x", ticks=(40, 50, 60, 80, 100, 120, 160))
    ax.set_xlabel("Hand-tapped tempo (BPM)")
    ax.set_ylabel("Analysed tempo (BPM)")
    ax.set_title(f"Octave corrections (n = {len(fix)})", loc="left", fontsize=10, color=INK)
    ax.legend(loc="upper left", fontsize=7.5)
    save(fig, "fig5_octave_corrections")


# =============================================================================
# MAIN
# =============================================================================
def main():
    d = load()
    sample_and_descriptives(d)

    say("\n== 3-4 Mixed models (" + ("log2 BPM" if USE_LOG else "BPM")
        + ", random intercept per participant) ==")
    o = models(d)
    report_models(o, MAIN_LABEL)
    TABLES["M1 song type"] = o["m1"]
    TABLES["M1 contrasts"] = o["contrasts"]
    TABLES["M3 song x continent"] = o["m3"]
    lrts = [{"analysis": MAIN_LABEL, "test": k, "chi2": o[k][0], "df": o[k][1], "p": o[k][2]}
            for k in ("song_lrt", "continent_lrt", "interaction_lrt")]

    say("\n== 3b Random-slopes check (unstructured within-participant covariance) ==")
    uc = unstructured_check(d)
    if uc is not None:
        TABLES["Random slopes check"] = uc

    lullaby_continents(d)

    say("\n== 5 Paired within-participant comparisons ==")
    pc = paired(d)
    report_paired(pc)

    covariates(d)

    say("\n== 8 Sensitivity ==")
    dr = d.copy()
    dr["y"] = dr["y_alt"]
    dr["bpm"] = dr["bpm_alt"]
    dn = d[~d.corrected]
    pr = paired(dr, label=ALT_LABEL)
    pn = paired(dn, label=FLAG_LABEL)
    contrasts = [o["contrasts"]]
    for lab, data in ((ALT_LABEL, dr), (FLAG_LABEL, dn)):
        o2 = models(data, label=lab)
        report_models(o2, lab)
        contrasts.append(o2["contrasts"])
        lrts += [{"analysis": lab, "test": k, "chi2": o2[k][0], "df": o2[k][1], "p": o2[k][2]}
                 for k in ("song_lrt", "continent_lrt", "interaction_lrt")]
    report_paired(pr)
    report_paired(pn)
    TABLES["M1 contrasts"] = pd.concat(contrasts, ignore_index=True)
    TABLES["Paired comparisons"] = pd.concat([pc, pr, pn], ignore_index=True)
    TABLES["Model LRTs"] = pd.DataFrame(lrts)

    statsmodels_check(d)

    style()
    fig_song_types(d)
    fig_paired(d)
    fig_continents(d)
    if MAKE_COUNTRY_FIGURE:
        fig_countries(d)
    fig_corrections(d)

    out_x = os.path.join(OUT_DIR, "results.xlsx")
    order = ["Sample", "Demographics", "Descriptives", "Descriptives continent", "M1 song type",
             "M1 contrasts", "Model LRTs", "M3 song x continent", "Continent tests",
             "Paired comparisons", "Covariates LRT", "Covariates model"]
    order += [k for k in TABLES if k not in order]
    with pd.ExcelWriter(out_x, engine="openpyxl") as xw:
        for k in order:
            if k in TABLES:
                TABLES[k].round(4).to_excel(xw, sheet_name=k[:31], index=False)
    with open(os.path.join(OUT_DIR, "report.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(REPORT))
    print(f"\nSaved: {out_x}\n       {os.path.join(OUT_DIR, 'report.txt')}\n       {os.path.join(OUT_DIR, 'figures')}")


if __name__ == "__main__":
    main()
