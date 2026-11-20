"""Static charts (PNG) for the README and the report."""
from __future__ import annotations

import pathlib

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

# Validated categorical palette (fixed order, never cycled) + neutral for "Other".
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTHER = "#b4b2ab"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e6e5e0"
SEQ = LinearSegmentedColormap.from_list(
    "trendwaves_blue", ["#fcfcfb", "#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#184f95", "#0d366b"]
)

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.size": 11,
        "font.family": "DejaVu Sans",
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "legend.frameon": False,
    }
)


def colors_for(categories: list[str]) -> dict[str, str]:
    """Stable colour per category: slots follow the given order; 'Other' is always grey."""
    out, slot = {}, 0
    for c in categories:
        if c in ("Other", "Unclassified"):
            out[c] = OTHER
        elif slot < len(PALETTE):
            out[c] = PALETTE[slot]
            slot += 1
        else:
            out[c] = OTHER
    return out


def _month_axis(ax):
    loc = mdates.MonthLocator()
    ax.xaxis.set_major_locator(loc)
    fmt = mdates.ConciseDateFormatter(loc, formats=["%Y", "%b", "%d", "%H:%M", "%H:%M", "%S.%f"],
                                      zero_formats=["", "%b\n%Y", "%b", "%b-%d", "%H:%M", "%H:%M"])
    ax.xaxis.set_major_formatter(fmt)


def _title(fig, ax, title: str, subtitle: str):
    ax.set_title(title, loc="left", fontsize=17, color=INK, pad=30, fontweight="bold")
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=10.5, color=INK_2, va="bottom")


def _footer(fig, text: str):
    fig.text(0.01, 0.005, text, fontsize=8.5, color=INK_2, ha="left", va="bottom")


def topic_panels(shares: pd.DataFrame, waves: pd.DataFrame, colors: dict, path: pathlib.Path, footer: str,
                 window: int):
    """Small multiples: one panel per topic, each on its own y-scale, detected waves shaded."""
    cats = [c for c in shares.columns if c != "Other"]
    ncol = 2
    nrow = -(-len(cats) // ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(15, 2.35 * nrow + 1.6), sharex=True, squeeze=False)
    for ax, c in zip(axes.flat, cats, strict=False):
        y = shares[c] * 100
        for _, w in waves[waves["category"] == c].iterrows():
            ax.axvspan(pd.Timestamp(w["start"]), pd.Timestamp(w["end"]), color=colors[c], alpha=0.12, lw=0)
            ax.scatter([pd.Timestamp(w["peak"])], [y.loc[pd.Timestamp(w["peak"])]], s=34, color=colors[c],
                       edgecolor=SURFACE, linewidth=2, zorder=5)
        ax.plot(y.index, y, color=colors[c], lw=2, solid_capstyle="round")
        ax.set_ylim(0, max(5, float(np.nanmax(y)) * 1.15))
        ax.set_title(f"{c}", loc="left", fontsize=12, color=INK, fontweight="bold", pad=4)
        ax.text(1, 1.02, f"avg {np.nanmean(y):.1f}%", transform=ax.transAxes, ha="right", va="bottom",
                fontsize=9.5, color=INK_2)
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
        ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(3))
        _month_axis(ax)
    for ax in list(axes.flat)[len(cats):]:
        ax.set_visible(False)
    h = fig.get_figheight()
    fig.suptitle("Topic heat on GitHub Trending", x=0.01, y=1 - 0.15 / h, ha="left", va="top", fontsize=17,
                 fontweight="bold", color=INK)
    fig.text(0.01, 1 - 0.62 / h,
             f"Share of daily Trending points ({window}-day mean), {shares.index[0]:%d %b %Y} – "
             f"{shares.index[-1]:%d %b %Y}. Each panel has its own scale; shaded bands are detected waves.",
             fontsize=10.5, color=INK_2, ha="left", va="top")
    _footer(fig, footer)
    fig.tight_layout(rect=(0, 0.3 / h, 1, 1 - 0.95 / h), h_pad=1.6)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def subtopic_share_area(shares: pd.DataFrame, colors: dict, path: pathlib.Path, footer: str, title: str,
                        subtitle: str):
    """100% stacked area of subtopics within one topic (e.g. what *kind* of AI was trending)."""
    data = shares.fillna(0) * 100
    order = list(data.columns)
    fig, ax = plt.subplots(figsize=(15, 7))
    ax.stackplot(data.index, *[data[c] for c in order], labels=order, colors=[colors[c] for c in order],
                 edgecolor=SURFACE, linewidth=0.8)
    ax.set_ylim(0, 100)
    ax.set_xlim(data.index[0], data.index[-1])
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.set_axisbelow(False)
    ax.grid(axis="y", color=SURFACE, alpha=0.5)
    _month_axis(ax)
    _title(fig, ax, title, subtitle)
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], loc="upper left", bbox_to_anchor=(1.0, 1.0))
    _footer(fig, footer)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def streamgraph(shares: pd.DataFrame, colors: dict, path: pathlib.Path, footer: str, window: int):
    data = shares.fillna(0) * 100
    order = list(data.columns)
    fig, ax = plt.subplots(figsize=(15, 7.5))
    ax.stackplot(data.index, *[data[c] for c in order], labels=order, colors=[colors[c] for c in order],
                 baseline="wiggle", edgecolor=SURFACE, linewidth=0.6)
    ax.set_yticks([])
    ax.grid(False)
    _month_axis(ax)
    _title(fig, ax, "How attention is shared between topics",
           f"Streamgraph of each topic's share of daily Trending points ({window}-day mean); band thickness = share")
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], loc="upper left", bbox_to_anchor=(1.0, 1.0))
    _footer(fig, footer)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def subtopic_heatmap(raw: pd.DataFrame, topic_of: dict, path: pathlib.Path, footer: str, max_rows: int = 22):
    """Weekly heat per subtopic, rows ordered by when each subtopic peaked -> waves read left to right."""
    weekly = raw.resample("W-MON", label="left", closed="left").mean()
    weekly = weekly.rolling(3, center=True, min_periods=1).mean()  # 3-week smoothing
    weekly = weekly[[c for c in weekly.columns if c != "Unclassified"]]
    keep = weekly.sum().sort_values(ascending=False).index[:max_rows]
    weekly = weekly[keep]
    share = weekly.div(weekly.max(), axis=1)  # each row normalised to its own peak
    peak_week = weekly.idxmax()
    order = peak_week.sort_values(kind="stable").index
    share = share[order]
    fig, ax = plt.subplots(figsize=(15, 0.36 * len(order) + 2.2))
    x = mdates.date2num(share.index.to_pydatetime())
    step = x[1] - x[0] if len(x) > 1 else 7
    edges = np.append(x, x[-1] + step)
    ax.pcolormesh(edges, np.arange(len(order) + 1), share.T.to_numpy(), cmap=SEQ, vmin=0, vmax=1,
                  edgecolors=SURFACE, linewidth=1.2)
    ax.set_yticks(np.arange(len(order)) + 0.5)
    ax.set_yticklabels([f"{s}  ·  {topic_of.get(s, '')}" for s in order], fontsize=9.5)
    ax.invert_yaxis()
    ax.grid(False)
    ax.xaxis_date()
    _month_axis(ax)
    ax.tick_params(axis="y", length=0)
    _title(fig, ax, "Waves, one after another",
           "Weekly points per subtopic (3-week smoothing), each row scaled to its own peak; "
           "rows sorted by peak week.")
    sm = plt.cm.ScalarMappable(cmap=SEQ, norm=plt.Normalize(0, 1))
    cb = fig.colorbar(sm, ax=ax, fraction=0.02, pad=0.01)
    cb.set_ticks([0, 0.5, 1])
    cb.set_ticklabels(["0", "50%", "peak"])
    cb.outline.set_visible(False)
    _footer(fig, footer)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def wave_timeline(waves: pd.DataFrame, topic_of: dict, colors: dict, path: pathlib.Path, footer: str,
                  max_rows: int = 28):
    """Gantt chart of the strongest subtopic waves, each labelled with the repo that led it."""
    if waves.empty:
        return
    w = waves.sort_values("wave_points", ascending=False).head(max_rows).sort_values("start").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(15, 0.42 * len(w) + 2.2))
    ax.set_axisbelow(True)
    for i, r in w.iterrows():
        s, e, p = (mdates.date2num(pd.Timestamp(r[k])) for k in ("start", "end", "peak"))
        col = colors.get(topic_of.get(r["category"], "Other"), OTHER)
        ax.barh(i, e - s + 1, left=s, height=0.62, color=col, alpha=0.9)
        ax.plot([p, p], [i - 0.31, i + 0.31], color=INK, lw=1.4)
        ax.text(e + 3, i, f"{r['lead_repository']}", va="center", fontsize=8.8, color=INK_2)
    ax.set_yticks(range(len(w)))
    ax.set_yticklabels(w["category"], fontsize=9.5)
    ax.invert_yaxis()
    ax.grid(axis="x", color=GRID)
    ax.grid(axis="y", visible=False)
    ax.xaxis_date()
    _month_axis(ax)
    ax.tick_params(axis="y", length=0)
    lo = mdates.date2num(pd.Timestamp(w["start"].min()))
    hi = mdates.date2num(pd.Timestamp(w["end"].max()))
    ax.set_xlim(lo - 5, hi + 60)
    used = [t for t in colors if any(topic_of.get(c) == t for c in w["category"])]
    from matplotlib.patches import Patch
    ax.legend([Patch(color=colors[t]) for t in used], used, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    _title(fig, ax, "Detected subtopic waves",
           f"The {len(w)} biggest waves by points earned · bar = wave duration, tick = peak, label = repo that led it")
    _footer(fig, footer)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=160)
    plt.close(fig)
