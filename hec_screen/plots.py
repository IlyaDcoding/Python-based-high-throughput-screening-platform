"""Headless Matplotlib figures with units and condition labels."""

import math
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import pandas as pd

COLORS = ("#174D69", "#087F77", "#B35036", "#67528B")
STYLE = {
    "figure.facecolor": "#F5F8FA", "axes.facecolor": "white", "axes.spines.top": False,
    "axes.spines.right": False, "axes.spines.left": False, "axes.edgecolor": "#B6C4CD",
    "axes.labelcolor": "#213440", "text.color": "#172F3C", "xtick.color": "#314957",
    "ytick.color": "#314957", "font.family": "DejaVu Sans", "font.size": 10,
    "grid.color": "#DBE4E9", "grid.linewidth": 0.7, "axes.axisbelow": True,
}
LABELS = {"thermal_expansion": "Thermal expansion coefficient", "youngs_modulus": "Young’s modulus"}
PLOT_UNITS = {"W/(m*K)": "W/(m·K)", "1e-6/K": "10⁻⁶ K⁻¹"}


def _label(prop):
    return LABELS.get(prop, prop.replace("_", " ").capitalize())


def _condition(row):
    if pd.isna(row["temperature_c"]):
        return "Temperature unspecified"
    if pd.notna(row["temperature_start_c"]):
        return f"{row['temperature_start_c']:g}–{row['temperature_c']:g} °C"
    return f"{row['temperature_c']:g} °C"


def _footer(fig, text):
    fig.text(0.04, 0.035, text, fontsize=9, color="#314957", va="bottom")


def _save(fig, path):
    fig.savefig(path, dpi=165)
    plt.close(fig)


def save_plots(result, output, top):
    """Plot a manageable number of candidates and keep full tables in the export."""
    rankings = result["rankings"].head(min(top, 12))
    criteria = result["criteria"].query("weight > 0").to_dict("records")
    evidence = result["evidence"]
    origin = result["filters"]["origin"].capitalize()
    application = result["filters"]["application"].capitalize()
    context = " · ".join(filter(None, (application, origin)))
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(8.2, max(3.4, 2 + 0.39 * len(rankings))))
        fig.subplots_adjust(left=0.25, bottom=0.23, right=0.94, top=0.78)
        fig.suptitle("Candidate ranking", x=0.04, y=0.96, ha="left", fontweight="bold", fontsize=19)
        if rankings.empty:
            ax.text(0.5, 0.5, "No eligible candidates", transform=ax.transAxes, ha="center", va="center")
        else:
            labels = [f"#{row.rank}  {row.material_id}" for row in rankings.itertuples()]
            bars = ax.barh(labels, rankings["score"], height=0.5, color=COLORS[0])
            ax.bar_label(bars, fmt="%.3f", padding=4)
            ax.invert_yaxis()
        ax.set(xlim=(0, 1.14), xlabel="Weighted score")
        ax.set_xticks([0, .25, .5, .75, 1])
        ax.grid(axis="x")
        _footer(fig, f"{context} | {len(rankings)} of {len(result['rankings'])} ranked specimens shown")
        _save(fig, output / "ranking.png")

        ncols = min(2, len(criteria))
        nrows = math.ceil(len(criteria) / ncols)
        height = 2.8 * nrows + 1.4
        fig, axes = plt.subplots(nrows, ncols, figsize=(5.1 * ncols, height), squeeze=False)
        fig.subplots_adjust(left=0.14 if ncols == 1 else 0.11, right=0.95, bottom=0.77 / height,
                            top=1 - 1.15 / height, wspace=0.30, hspace=0.80)
        fig.suptitle("Properties of shortlisted candidates", x=0.04, y=0.96, ha="left", fontweight="bold", fontsize=17)
        for index, (ax, row) in enumerate(zip(axes.flat, criteria)):
            prop = row["property"]
            values = rankings[prop]
            ax.set_title(f"{_label(prop)}\n{_condition(row)} · {row['direction']}", fontsize=11)
            ax.set_ylabel(PLOT_UNITS.get(row["unit"], row["unit"]))
            ax.grid(axis="y")
            if rankings.empty:
                ax.text(0.5, 0.5, "No eligible candidates", transform=ax.transAxes, ha="center", va="center")
                ax.set_xticks([])
                continue
            labels = rankings["material_id"] if len(rankings) <= 4 else list(range(1, len(rankings) + 1))
            ax.scatter(labels, values, s=46, zorder=3, color=COLORS[index % len(COLORS)])
            ax.margins(x=0.13, y=0.15)
            subset = evidence.loc[evidence["property"].eq(prop)].set_index("material_id")
            for label, material, value in zip(labels, rankings["material_id"], values):
                uncertainty = subset.loc[material, "uncertainty_canonical"]
                if pd.notna(uncertainty):
                    ax.errorbar(label, value, yerr=uncertainty, color=COLORS[index % len(COLORS)], capsize=4)
        for ax in list(axes.flat)[len(criteria):]:
            ax.set_visible(False)
        note = " | Positions follow ranking chart order" if len(rankings) > 4 else ""
        _footer(fig, f"{context}{note}")
        _save(fig, output / "properties.png")

        scenarios = result["sensitivity"]
        scenario_count = max(1, scenarios["scenario"].nunique())
        fig, ax = plt.subplots(figsize=(max(8.2, 1.38 * scenario_count), 4.6))
        fig.subplots_adjust(left=0.14, bottom=0.26, right=0.94, top=0.81)
        fig.suptitle("Sensitivity to criterion weights", x=0.04, y=0.96, ha="left", fontweight="bold", fontsize=18)
        for index, material in enumerate(rankings["material_id"]):
            subset = scenarios.loc[scenarios["material_id"].eq(material)]
            ax.plot(subset["scenario"], subset["rank"], marker="o", linewidth=1.6,
                    color=COLORS[index % len(COLORS)], label=material)
        if rankings.empty:
            ax.text(0.5, 0.5, "No eligible candidates", transform=ax.transAxes, ha="center", va="center")
        elif len(rankings) <= 8:
            ax.legend(loc="best", frameon=False, ncol=min(3, len(rankings)), fontsize=8)
        ax.set_ylabel("Rank")
        ax.set_ylim(max(1.5, len(result["rankings"]) + 0.35), 0.65)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=8))
        if not rankings.empty:
            handles = ["Baseline"]
            for case in scenarios["scenario"].unique()[1:]:
                prop, change = case.rsplit(" ", 1)
                label = "Thermal expansion" if prop == "thermal_expansion" else _label(prop)
                handles.append(f"{textwrap.fill(label, width=18)}\n{change}")
            ax.set_xticks(range(len(handles)), handles, fontsize=8)
        ax.grid(axis="y")
        _footer(fig, "One weight changed by ±20% before renormalization. Screening pool held fixed.")
        _save(fig, output / "sensitivity.png")

