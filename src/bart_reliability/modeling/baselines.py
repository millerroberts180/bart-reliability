"""Baselines: no revision, and historical medians and frequencies from training rows."""

from __future__ import annotations

import numpy as np
import pandas as pd

from bart_reliability.modeling.config import LeakageError

GLOBAL_LEVEL = "all_training_rows"


class NoRevisionBaseline:
    """Predicts that the published ETA will not change: 0 s, never a large revision."""

    name = "no_revision"

    def predict(self, rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        n = len(rows)
        return np.zeros(n), np.zeros(n)


class HistoricalBaseline:
    """Median revision and large-revision frequency by group, fitted on training rows only.

    Groups are tried in `levels` order. A group with fewer than `min_group_size`
    training rows (or one never seen in training) defers to the next level. The last
    level, all training rows, always applies.
    """

    name = "historical"

    def __init__(self, levels: tuple[tuple[str, ...], ...], min_group_size: int):
        self.levels = levels
        self.min_group_size = min_group_size
        self.tables: list[pd.DataFrame] | None = None
        self.global_stats: dict | None = None

    def fit(self, rows: pd.DataFrame) -> HistoricalBaseline:
        splits = set(rows["split"].unique())
        if splits != {"train"}:
            raise LeakageError(
                f"historical baseline must be fitted on training rows only: {splits}"
            )
        self.tables = []
        for i, keys in enumerate(self.levels):
            stats = (
                rows.groupby(list(keys), observed=True)
                .agg(
                    n=("eta_revision_seconds", "size"),
                    median_revision_s=("eta_revision_seconds", "median"),
                    large_revision_rate=("large_revision", "mean"),
                )
                .reset_index()
            )
            stats = stats[stats["n"] >= self.min_group_size].assign(level=i)
            self.tables.append(stats)
        self.global_stats = {
            "n": len(rows),
            "median_revision_s": float(rows["eta_revision_seconds"].median()),
            "large_revision_rate": float(rows["large_revision"].mean()),
        }
        return self

    def predict(self, rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Returns (median revision, large-revision probability, level name) per row."""
        if self.tables is None:
            raise RuntimeError("fit the baseline first")
        n = len(rows)
        revision = np.full(n, np.nan)
        probability = np.full(n, np.nan)
        level = np.full(n, GLOBAL_LEVEL, dtype=object)
        for keys, table in zip(self.levels, self.tables, strict=True):
            todo = np.isnan(revision)
            if not todo.any():
                break
            matched = rows.loc[todo, list(keys)].merge(table, on=list(keys), how="left")
            found = matched["n"].notna().to_numpy()
            idx = np.flatnonzero(todo)[found]
            revision[idx] = matched.loc[found, "median_revision_s"].to_numpy()
            probability[idx] = matched.loc[found, "large_revision_rate"].to_numpy()
            level[idx] = "+".join(keys)
        rest = np.isnan(revision)
        revision[rest] = self.global_stats["median_revision_s"]
        probability[rest] = self.global_stats["large_revision_rate"]
        return revision, probability, level

    def fitted_groups(self) -> pd.DataFrame:
        """Every fitted group with its level, for the artifact and for audits."""
        frames = []
        for keys, table in zip(self.levels, self.tables, strict=True):
            t = table.copy()
            t["level_name"] = "+".join(keys)
            # Works for an empty level too (no group reached min_group_size).
            t["group_key"] = [
                "|".join(map(str, row)) for row in t[list(keys)].itertuples(index=False)
            ]
            frames.append(
                t[
                    [
                        "level",
                        "level_name",
                        "group_key",
                        "n",
                        "median_revision_s",
                        "large_revision_rate",
                    ]
                ]
            )
        frames.append(
            pd.DataFrame(
                [
                    {
                        "level": len(self.levels),
                        "level_name": GLOBAL_LEVEL,
                        "group_key": "",
                        **self.global_stats,
                    }
                ]
            )
        )
        return pd.concat(frames, ignore_index=True)


def fit_sensitivity(
    train: pd.DataFrame, levels: tuple[tuple[str, ...], ...], sizes: tuple[int, ...]
) -> dict[int, HistoricalBaseline]:
    """One historical baseline per predeclared minimum group size.

    Every version uses the same fallback hierarchy and is fitted on training rows only
    (fit() refuses anything else). The results are reported, never used to choose a size.
    """
    return {size: HistoricalBaseline(levels, size).fit(train) for size in sizes}
