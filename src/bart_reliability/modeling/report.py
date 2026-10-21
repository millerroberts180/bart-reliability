"""Human-readable report.md for a modeling run, written from metrics.json data."""

from __future__ import annotations

from pathlib import Path

HORIZON_NOTE = (
    "Horizons are **published-time horizons**: 5, 10 and 15 minutes are what BART's own ETA "
    "said at the prediction snapshot (within ±60 s), not independently observed time before "
    "physical arrival."
)


def _fmt(v, digits: int = 3) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{digits}f}" if abs(v) < 10 else f"{v:.1f}"
    return str(v)


def _table(header: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(_fmt(c) for c in r) + " |" for r in rows]
    return out + [""]


def _sample_cols(block: dict) -> list:
    return [block["examples"], block["events"], " to ".join(block["service_dates"])]


def _role(name: str, task: str, metrics: dict) -> str:
    selection = metrics["selection"][task]
    locked = metrics.get("locked_comparison")
    if locked and name == locked["name"]:
        return f"locked earlier model `{locked[task]}`, never refitted"
    if name in ("no_revision", "historical"):
        return "baseline"
    if name == selection["selected"]:
        return f"selected ({selection['criterion']})"
    if name.startswith("linear"):
        return "linear comparator"
    return "tree candidate"


def _pct(share: float) -> str:
    return f"{100 * share:.1f}%"


def _ci(d: dict, digits: int = 3) -> str:
    return f"{_fmt(d['ci_low'], digits)} to {_fmt(d['ci_high'], digits)}"


def write_report(path: Path, metrics: dict, manifest: dict) -> None:
    sel = metrics["selection"]
    reg, cls = sel["regression"]["selected"], sel["classification"]["selected"]
    comp = metrics["linear_comparator"]
    lines = ["# ETA revision models: development run", "", f"**{metrics['note']}**", ""]
    wh = manifest["warehouse_data"]
    lines += [
        "## How to read this report",
        "",
        f"- {HORIZON_NOTE}",
        "- Targets are revisions relative to BART's own final stable published estimate.",
        f"- The regression model `{reg}` was selected using validation MAE, and the "
        f"classifier `{cls}` using validation Brier score. Models were not refitted on "
        "validation data. Only these two and the baselines were scored on test.",
        f"- {comp['description']} The best linear candidate, `{comp['model']}`, was "
        + ("selected." if comp["selected"] else "not selected."),
        f"- Precision and recall use a probability of {metrics['decision_threshold']} as a "
        "descriptive operating point, not an optimized deployment threshold. A production "
        "threshold would be selected on validation data using an explicit rider or product "
        "cost.",
        f"- Large revision: |revision| > {metrics['large_revision_threshold_s']} s. Warehouse "
        f"snapshots: {wh['trip_update_snapshots']} ({wh['first_snapshot_utc']} to "
        f"{wh['last_snapshot_utc']}).",
        "",
        "## Splits",
        "",
    ]
    lines += _table(
        [
            "Split",
            "Service dates",
            "Predictions (UTC)",
            "Events",
            "Trips",
            "Examples",
            "5 / 10 / 15 min (published-time)",
            "Large-revision prevalence",
        ],
        [
            [
                name,
                " to ".join(s["service_dates"]),
                f"{s['predictions_from_utc']} to {s['predictions_to_utc']}",
                s["events"],
                s.get("trips", "n/a"),
                s["examples"],
                " / ".join(str(v) for v in s["examples_by_horizon"].values()),
                s["large_revision_prevalence"],
            ]
            for name, s in metrics["samples"].items()
        ],
    )
    ex = metrics["exclusions"]
    lines += ["## Exclusions", ""]
    lines += _table(
        ["Stage", "Reason", "Count"],
        [
            *(
                ["warehouse event not eligible", k, v]
                for k, v in ex["warehouse_events_not_eligible"].items()
            ),
            *(
                ["eligible event-horizon without example", k, v]
                for k, v in ex["eligible_event_horizons_without_example"].items()
            ),
            *(["example", k, v] for k, v in ex["examples_by_frame_exclusion"].items()),
            *(
                ["example outside split dates", k, v]
                for k, v in ex["examples_outside_split_dates_by_service_date"].items()
            ),
        ],
    )

    for split in ("validation", "test"):
        block = metrics[split]
        title = (
            "Validation (all candidates)"
            if split == "validation"
            else ("Test (selected models and baselines, evaluated once)")
        )
        lines += [f"## {title}", "", "### Revision magnitude (seconds)", ""]
        reg_rows = []
        for name, r in block["regression"].items():
            o = r["overall"]
            per = [r["by_horizon"][h]["mae_s"] for h in r["by_horizon"]]
            reg_rows.append(
                [
                    name,
                    _role(name, "regression", metrics),
                    o["mae_s"],
                    o["median_ae_s"],
                    o["rmse_s"],
                    o["mean_error_s"],
                    " / ".join(_fmt(v) for v in per),
                    *_sample_cols(o),
                ]
            )
        lines += _table(
            [
                "Model",
                "Role",
                "MAE",
                "Median AE",
                "RMSE",
                "Mean error",
                "MAE at 5 / 10 / 15 min published-time horizon",
                "Examples",
                "Events",
                "Service dates",
            ],
            reg_rows,
        )
        lines += ["### Large revisions", ""]
        cls_rows = []
        for name, c in block["classification"].items():
            o = c["overall"]
            per = [c["by_horizon"][h]["pr_auc"] for h in c["by_horizon"]]
            cls_rows.append(
                [
                    name,
                    _role(name, "classification", metrics),
                    o["prevalence"],
                    o["precision"],
                    o["recall"],
                    o["pr_auc"],
                    o["roc_auc"],
                    o["brier"],
                    o["ece"],
                    " / ".join(_fmt(v) for v in per),
                    *_sample_cols(o),
                ]
            )
        lines += _table(
            [
                "Model",
                "Role",
                "Prevalence",
                "Precision at operating point",
                "Recall at operating point",
                "PR-AUC",
                "ROC-AUC",
                "Brier",
                "ECE",
                "PR-AUC at 5 / 10 / 15 min published-time horizon",
                "Examples",
                "Events",
                "Service dates",
            ],
            cls_rows,
        )

    lines += ["## Selection (validation only)", ""]
    lines += [
        f"- Regression: **{reg}**, selected using {sel['regression']['criterion']}.",
        f"- Classification: **{cls}**, selected using {sel['classification']['criterion']}.",
        "- Models were not refitted on validation data.",
        "",
    ]

    unc = metrics["uncertainty"]
    level = f"{int(unc['confidence_level'] * 100)}% interval"

    def uncertainty_table(block, key="selected_minus_historical"):
        d = block[key]
        rows = [["MAE (s), overall", d["mae_s"]["overall"]]]
        rows += [
            [f"MAE (s), {int(h) // 60}-min published-time horizon", v]
            for h, v in d["mae_s"]["by_horizon"].items()
        ]
        rows += [["Brier score", d["brier"]], ["PR-AUC", d["pr_auc"]]]
        return _table(
            [
                "Difference",
                "Observed",
                level,
                "Replicates where the selected model wins",
                "Reading",
            ],
            [
                # Four decimals: the Brier and PR-AUC differences are small.
                [
                    label,
                    _fmt(v["observed"], 4),
                    _ci(v, 4),
                    _pct(v["share_of_replicates_model_better"]),
                    v["interpretation"],
                ]
                for label, v in rows
            ],
        )

    trip, event = unc["primary_trip_clustered"], unc["sensitivity_event_clustered"]
    lines += [
        "## Test uncertainty (primary): trip-clustered bootstrap",
        "",
        f"Selected models minus the historical baseline. {unc['method'].capitalize()} with "
        f"{unc['replicates']} replicates (seed {unc['seed']}), resampling "
        f"{trip['clusters']} trip runs ({unc['events']} events, {unc['examples']} examples, "
        f"{' to '.join(unc['service_dates'])}). Unit: {trip['resampling_unit']}. Negative "
        "MAE and Brier differences and positive PR-AUC differences favor the selected model.",
        "",
        f"**Scope.** {trip['note']}",
        "",
    ]
    lines += uncertainty_table(trip)
    lines += [
        "## Sensitivity: event-clustered bootstrap",
        "",
        f"{event['note']} Resampled {event['clusters']} events; unit: "
        f"{event['resampling_unit']}. Same seed and replicate count as the primary table.",
        "",
    ]
    lines += uncertainty_table(event)

    locked = metrics.get("locked_comparison")
    if locked:
        key = f"selected_minus_{locked['name']}"
        lines += [
            f"## Test: retrained models minus the locked models (`{locked['name']}`)",
            "",
            f"Locked bundle `{locked['bundle_id']}` (model version `{locked['model_version']}`): "
            f"regression `{locked['regression']}`, classification `{locked['classification']}`, "
            f"trained on {' to '.join(locked['train_service_dates'])} and selected on "
            f"{' to '.join(locked['validation_service_dates'])}. Loaded through the bundle "
            "verifier and only used to predict on the test rows; never refitted. Same paired "
            "resamples as above. Negative MAE and Brier differences and positive PR-AUC "
            "differences favor the retrained model.",
            "",
            "**Primary: trip-clustered**",
            "",
        ]
        lines += uncertainty_table(trip, key)
        lines += ["**Sensitivity: event-clustered**", ""]
        lines += uncertainty_table(event, key)

    support = metrics.get("category_support")
    if support:
        t = support["test"]
        lines += ["## Category support and fallback (test)", "", t["rule"], ""]
        rows = []
        for model, d in t["outside_support"].items():
            unseen = "; ".join(
                f"{f}: " + ", ".join(f"{v} ({n})" for v, n in vals.items())
                for f, vals in d["unseen_values_by_feature"].items()
            )
            rows.append(
                [
                    model,
                    d["examples"],
                    _pct(d["share_of_examples"]),
                    d["events"],
                    d["trips"],
                    unseen or "none",
                ]
            )
        sh = t["shared_support"]
        rows.append(
            [
                "inside every model's support (shared)",
                sh["examples"],
                _pct(sh["share_of_examples"]),
                sh["events"],
                sh["trips"],
                "",
            ]
        )
        lines += _table(
            [
                "Model",
                "Examples outside support",
                "Share of test examples",
                "Events",
                "Trips",
                "Unseen values (examples)",
            ],
            rows,
        )
        v = support["validation_selected_only"]["outside_support"]["selected"]
        lines += [
            f"Validation rows outside the selected models' support: {v['examples']} "
            f"({_pct(v['share_of_examples'])}).",
            "",
        ]
    subset = metrics.get("shared_support_subset")
    if subset and subset["computed"]:
        sm = subset["metrics"]
        lines += [
            "## Shared-support subset (test)",
            "",
            subset["description"],
            "",
        ]
        lines += _table(
            ["Model", "MAE", "MAE at 5 / 10 / 15 min", "Examples", "Events", "Service dates"],
            [
                [
                    name,
                    r["overall"]["mae_s"],
                    " / ".join(_fmt(r["by_horizon"][h]["mae_s"]) for h in r["by_horizon"]),
                    *_sample_cols(r["overall"]),
                ]
                for name, r in sm["regression"].items()
            ],
        )
        lines += _table(
            ["Model", "Brier", "PR-AUC"],
            [
                [name, c["overall"]["brier"], c["overall"]["pr_auc"]]
                for name, c in sm["classification"].items()
            ],
        )
        keys = [k for k in subset["primary_trip_clustered"] if k.startswith("selected_minus_")]
        for k in keys:
            lines += [f"**{k.replace('_', ' ')}: trip-clustered (primary)**", ""]
            lines += uncertainty_table(subset["primary_trip_clustered"], k)
            lines += [f"**{k.replace('_', ' ')}: event-clustered (sensitivity)**", ""]
            lines += uncertainty_table(subset["sensitivity_event_clustered"], k)
    elif subset:
        lines += ["## Shared-support subset (test)", "", f"Not computed: {subset['reason']}.", ""]

    sens = metrics["historical_baseline_sensitivity"]
    lines += [
        "## Historical-baseline sensitivity (predeclared minimum group sizes)",
        "",
        f"{sens['note']} Primary: {sens['primary_min_group_size']}. Intervals are "
        "trip-clustered, as in the primary uncertainty table.",
        "",
    ]
    srows = []
    for size, e in sens["settings"].items():
        b = e["test"]["paired_trip_bootstrap"]
        srows.append(
            [
                size,
                e["primary"],
                e["validation"]["selected_minus_historical"]["mae_s"],
                e["test"]["historical_mae_s"],
                b["mae_s"]["overall"]["observed"],
                _ci(b["mae_s"]["overall"]),
                b["brier"]["observed"],
                _ci(b["brier"]),
                b["pr_auc"]["observed"],
                _ci(b["pr_auc"]),
            ]
        )
    lines += _table(
        [
            "Min group size",
            "Primary",
            "Validation MAE diff",
            "Test historical MAE",
            "Test MAE diff",
            "Interval",
            "Test Brier diff",
            "Interval",
            "Test PR-AUC diff",
            "Interval",
        ],
        srows,
    )
    same = sens["test_conclusion_same_for_every_setting"]
    lines += [
        "Test reading unchanged across settings: "
        + ", ".join(f"{k} {_fmt(v)}" for k, v in same.items())
        + ".",
        "",
    ]

    rel = metrics["test"]["relative_to_baselines"]
    lines += [
        "## Test: selected models relative to baselines (point differences)",
        "",
        "Model minus baseline; negative MAE, RMSE, Brier and ECE differences are improvements.",
        "",
    ]
    rows = []
    for task, keys in (
        ("regression", ("mae_s", "median_ae_s", "rmse_s")),
        ("classification", ("brier", "pr_auc", "roc_auc", "ece")),
    ):
        for base, r in rel[task].items():
            for scope, vals in [("overall", r["overall"]), *r["by_horizon"].items()]:
                for k in keys:
                    rows.append([task, base, scope, k, vals[k]["difference"], vals[k]["pct"]])
    lines += _table(
        ["Task", "Baseline", "Published-time horizon", "Metric", "Difference", "Percent"], rows
    )

    lines += ["## Test calibration", ""]
    for name, c in metrics["test"]["classification"].items():
        if name == "no_revision":
            continue
        lines += [f"**{name}** ({_role(name, 'classification', metrics)})", ""]
        lines += _table(
            ["Bin", "Examples", "Mean predicted", "Observed rate"],
            [
                [b["bin"], b["n"], b["mean_predicted"], b["observed_rate"]]
                for b in c["overall"]["calibration"]
            ],
        )

    levels = metrics["historical_baseline_levels_used"]
    lines += ["## Historical baseline fallback levels used (primary setting)", ""]
    lines += _table(
        ["Split", "Level", "Examples"], [[s, k, v] for s, d in levels.items() for k, v in d.items()]
    )
    status = "selected" if comp["selected"] else "not selected"
    lines += [f"## Linear comparator ({status}): `{comp['model']}`", "", comp["description"], ""]
    lines += _table(
        ["Feature", "Standardized coefficient (s per SD, or per category)"],
        [[c["feature"], c["coefficient"]] for c in comp["largest_standardized_coefficients"]],
    )
    alarm = metrics["single_feature_alarm"]
    lines += [
        "## Single-feature alarm",
        "",
        alarm["description"],
        f"The run fails if one feature alone reaches ROC-AUC {alarm['fails_at']} on training rows.",
        "",
    ]
    lines += _table(
        ["Feature", "Single-feature ROC-AUC (training rows)"],
        list(map(list, alarm["single_feature_roc_auc_train"].items())),
    )
    if metrics["fit_warnings"]:
        lines += ["## Fit warnings", ""]
        lines += [f"- {k}: {'; '.join(v)}" for k, v in metrics["fit_warnings"].items()] + [""]
    path.write_text("\n".join(lines))
