"""Historical-baseline sensitivity to its minimum group size (predeclared settings).

The primary setting stays the configured min_group_size. These results are descriptive:
they show whether the selected models' comparison with the baseline depends on the
setting, and they are never used to pick one.
"""

from __future__ import annotations

import pandas as pd

from bart_reliability.modeling.baselines import fit_sensitivity
from bart_reliability.modeling.metrics import classification_metrics, regression_metrics
from bart_reliability.modeling.uncertainty import compare


def baseline_name(size: int, primary: int) -> str:
    return "historical" if size == primary else f"historical_min{size}"


def sensitivity_predictions(
    train: pd.DataFrame, parts: dict[str, pd.DataFrame], cfg
) -> tuple[dict, dict]:
    """Fit every setting on training rows; predict each evaluation split.

    Returns ({size: fitted baseline}, {split: {size: (revision, probability, level)}}).
    """
    fitted = fit_sensitivity(train, cfg.baseline_levels, cfg.baseline_sensitivity_min_group_sizes)
    preds = {
        split: {size: b.predict(rows) for size, b in fitted.items()}
        for split, rows in parts.items()
    }
    return fitted, preds


def sensitivity_report(
    parts: dict[str, pd.DataFrame],
    preds: dict,
    fitted: dict,
    selected_reg: dict[str, object],
    selected_prob: dict[str, object],
    draws: dict,
    observed: dict,
    names: dict[str, str],
    cfg,
) -> dict:
    """Per setting: baseline metrics on validation and test, the selected models minus the
    baseline (validation observed; test with paired trip-clustered bootstrap intervals),
    and the fallback levels used."""
    primary = cfg.baseline_min_group_size
    settings = {}
    for size, model in fitted.items():
        entry = {"primary": size == primary, "fitted_groups_by_level": {}}
        groups = model.fitted_groups()
        entry["fitted_groups_by_level"] = {
            str(k): int(v) for k, v in groups.groupby("level_name")["n"].size().items()
        }
        for split, rows in parts.items():
            reg, prob, level = preds[split][size]
            y, yc = rows["eta_revision_seconds"].to_numpy(), rows["large_revision"].to_numpy()
            base_reg = regression_metrics(y, reg)
            base_cls = classification_metrics(yc, prob, cfg.decision_threshold)
            model_reg = regression_metrics(y, selected_reg[split])
            model_cls = classification_metrics(yc, selected_prob[split], cfg.decision_threshold)
            entry[split] = {
                "historical_mae_s": base_reg["mae_s"],
                "historical_brier": base_cls["brier"],
                "historical_pr_auc": base_cls["pr_auc"],
                "selected_minus_historical": {
                    "mae_s": round(model_reg["mae_s"] - base_reg["mae_s"], 4),
                    "brier": round(model_cls["brier"] - base_cls["brier"], 4),
                    "pr_auc": round(model_cls["pr_auc"] - base_cls["pr_auc"], 4),
                },
                "levels_used": {
                    str(k): int(v) for k, v in pd.Series(level).value_counts().sort_index().items()
                },
            }
        entry["test"]["paired_trip_bootstrap"] = compare(
            parts["test"],
            draws,
            observed,
            names["regression"],
            names["classification"],
            baseline_name(size, primary),
            cfg.bootstrap_confidence_level,
        )
        settings[str(size)] = entry

    def conclusions(metric, horizon=None):
        out = set()
        for e in settings.values():
            block = e["test"]["paired_trip_bootstrap"][metric]
            if metric == "mae_s":
                block = block["by_horizon"][horizon] if horizon else block["overall"]
            out.add(block["interpretation"])
        return out

    checks = {
        "mae_s": conclusions("mae_s"),
        **{
            f"mae_s_{h}": conclusions("mae_s", h)
            for h in settings[str(primary)]["test"]["paired_trip_bootstrap"]["mae_s"]["by_horizon"]
        },
        "brier": conclusions("brier"),
        "pr_auc": conclusions("pr_auc"),
    }
    return {
        "primary_min_group_size": primary,
        "min_group_sizes": list(cfg.baseline_sensitivity_min_group_sizes),
        "note": (
            "Predeclared settings, fitted on training rows only with the same fallback "
            "hierarchy. Reported for robustness; the primary setting is not changed by them."
        ),
        "settings": settings,
        "test_conclusion_same_for_every_setting": {k: len(v) == 1 for k, v in checks.items()},
    }
