"""Inference utilities for BeeSafe AI.

This module intentionally does not modify the source dataset or fit models.
It loads a previously saved Phase 08 deployment bundle and transforms one
SMILES string using the same RDKit feature settings used in Phase 03.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import math

import joblib
import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs, rdBase
from rdkit.Chem import Descriptors, rdMolDescriptors, rdFingerprintGenerator

DESCRIPTOR_NAMES = [
    "MolWt", "MolLogP", "TPSA", "NumHDonors", "NumHAcceptors",
    "RingCount", "HeavyAtomCount", "NumRotatableBonds",
    "NumAromaticRings", "FractionCSP3", "FormalCharge", "NumHeteroatoms",
]
MORGAN_RADIUS = 2
MORGAN_BITS = 2048
INCLUDE_CHIRALITY = False


def parse_smiles(smiles: str):
    """Parse a SMILES string; return a sanitised RDKit molecule or raise ValueError."""
    if not isinstance(smiles, str) or not smiles.strip():
        raise ValueError("Enter a non-empty SMILES string.")
    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        raise ValueError("RDKit could not parse this SMILES. Check the string for typos.")
    return mol


def canonicalize_smiles(mol) -> str:
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def molecular_descriptors(mol) -> dict[str, float]:
    """Calculate the exact ordered descriptor set used by Phase 03."""
    values = {
        "MolWt": Descriptors.MolWt(mol),
        "MolLogP": Descriptors.MolLogP(mol),
        "TPSA": Descriptors.TPSA(mol),
        "NumHDonors": Descriptors.NumHDonors(mol),
        "NumHAcceptors": Descriptors.NumHAcceptors(mol),
        "RingCount": rdMolDescriptors.CalcNumRings(mol),
        "HeavyAtomCount": mol.GetNumHeavyAtoms(),
        "NumRotatableBonds": Descriptors.NumRotatableBonds(mol),
        "NumAromaticRings": rdMolDescriptors.CalcNumAromaticRings(mol),
        "FractionCSP3": rdMolDescriptors.CalcFractionCSP3(mol),
        "FormalCharge": Chem.GetFormalCharge(mol),
        "NumHeteroatoms": Descriptors.NumHeteroatoms(mol),
    }
    if not all(math.isfinite(float(v)) for v in values.values()):
        raise ValueError("At least one molecular descriptor was non-finite.")
    return {k: float(v) for k, v in values.items()}


def morgan_fingerprint(mol) -> tuple[np.ndarray, Any]:
    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=MORGAN_RADIUS,
        fpSize=MORGAN_BITS,
        includeChirality=INCLUDE_CHIRALITY,
    )
    fp = generator.GetFingerprint(mol)
    arr = np.zeros((MORGAN_BITS,), dtype=np.int32)
    DataStructs.ConvertToNumpyArray(fp, arr)
    if not np.isin(arr, [0, 1]).all() or arr.sum() == 0:
        raise ValueError("Could not generate a valid non-empty Morgan fingerprint.")
    return arr.astype(np.uint8).reshape(1, -1), fp


def build_feature_row(mol, bundle: dict[str, Any]) -> tuple[np.ndarray, dict[str, float], np.ndarray, Any]:
    """Build a one-row matrix matching the saved bundle's expected feature type."""
    descriptors = molecular_descriptors(mol)
    fp_row, fp_obj = morgan_fingerprint(mol)
    feature_type = str(bundle.get("feature_type", "morgan")).lower()
    if feature_type == "morgan":
        X = fp_row
    elif feature_type in {"descriptors", "descriptor"}:
        descriptor_names = bundle.get("descriptor_names") or DESCRIPTOR_NAMES
        missing = [name for name in descriptor_names if name not in descriptors]
        if missing:
            raise ValueError(f"The saved model expects unknown descriptors: {missing}")
        X = np.asarray([[descriptors[name] for name in descriptor_names]], dtype=float)
    else:
        raise ValueError(f"Unsupported model feature type: {feature_type!r}")

    expected_width = bundle.get("feature_width")
    if expected_width is not None and X.shape[1] != int(expected_width):
        raise ValueError(
            f"Feature-width mismatch: this app created {X.shape[1]} features, "
            f"but the saved model expects {expected_width}."
        )
    return X, descriptors, fp_row, fp_obj


def apply_calibrator(calibrator, method: str, probability: np.ndarray) -> np.ndarray:
    p = np.asarray(probability, dtype=float).reshape(-1)
    method = (method or "sigmoid").lower()
    if method == "sigmoid":
        p_clip = np.clip(p, 1e-6, 1 - 1e-6)
        logits = np.log(p_clip / (1 - p_clip)).reshape(-1, 1)
        result = calibrator.predict_proba(logits)[:, 1]
    elif method == "isotonic":
        result = np.asarray(calibrator.predict(p), dtype=float).reshape(-1)
    else:
        raise ValueError(f"Unsupported calibration method in bundle: {method}")
    return np.clip(result, 0.0, 1.0)


def predict_positive_probability(bundle: dict[str, Any], X: np.ndarray) -> tuple[float, dict[str, Any]]:
    """Return toxic-label probability and useful model metadata."""
    if "model_pairs" in bundle:
        pair_probs = []
        for pair in bundle["model_pairs"]:
            estimator = pair["estimator"]
            raw = estimator.predict_proba(X)[:, 1]
            method = pair.get("calibration_method", bundle.get("calibration_method", "sigmoid"))
            calibrator = pair.get("calibrator")
            if calibrator is None:
                pair_probs.append(np.asarray(raw, dtype=float))
            else:
                pair_probs.append(apply_calibrator(calibrator, method, raw))
        if not pair_probs:
            raise ValueError("The saved calibrated ensemble contains no estimators.")
        p = float(np.mean(np.vstack(pair_probs), axis=0)[0])
        details = {
            "model_type": "Phase 08 calibrated ensemble",
            "base_model_family": bundle.get("model_family", "Ensemble"),
            "calibration_method": bundle.get("calibration_method", "per-fold calibration"),
            "training_records": bundle.get("training_data_rows"),
        }
    elif "model" in bundle:
        estimator = bundle["model"]
        p = float(estimator.predict_proba(X)[0, 1])
        details = {
            "model_type": "Phase 05 model (uncalibrated fallback)",
            "base_model_family": bundle.get("model_family", estimator.__class__.__name__),
            "calibration_method": "none",
            "training_records": bundle.get("training_rows"),
        }
    else:
        raise ValueError("Unrecognized model bundle. Expected 'model_pairs' or 'model'.")

    if not math.isfinite(p) or not (0.0 <= p <= 1.0):
        raise ValueError("The model returned an invalid prediction probability.")
    return p, details


def load_reference_data(npz_path: Path, metadata_path: Path):
    """Load baseline fingerprints and metadata for nearest-neighbour context."""
    if not npz_path.is_file() or not metadata_path.is_file():
        return None
    with np.load(npz_path, allow_pickle=False) as data:
        X_ref = data["X_morgan"].astype(np.uint8, copy=True)
        row_ids = data["source_row_index"].astype(np.int64, copy=True)
    meta = pd.read_csv(metadata_path)
    if len(X_ref) != len(meta) or len(row_ids) != len(meta):
        raise ValueError("Phase 03 reference fingerprints and metadata have different lengths.")
    if "source_row_index" in meta.columns:
        if not np.array_equal(row_ids, meta["source_row_index"].to_numpy(dtype=np.int64)):
            raise ValueError("Phase 03 reference features and metadata are not row-aligned.")
    if X_ref.ndim != 2 or X_ref.shape[1] != MORGAN_BITS:
        raise ValueError(f"Expected reference Morgan fingerprints with {MORGAN_BITS} bits.")
    ref_fps = [DataStructs.CreateFromBitString("".join(row.astype(str).tolist())) for row in X_ref]
    return {"fingerprints": ref_fps, "metadata": meta, "row_ids": row_ids}


def nearest_reference(query_fp, reference: dict[str, Any] | None) -> dict[str, Any] | None:
    if reference is None or not reference.get("fingerprints"):
        return None
    similarities = DataStructs.BulkTanimotoSimilarity(query_fp, reference["fingerprints"])
    idx = int(np.argmax(similarities))
    meta = reference["metadata"].iloc[idx]
    name = str(meta.get("name", "Reference compound"))
    return {
        "similarity": float(similarities[idx]),
        "name": name,
        "source_row_index": int(reference["row_ids"][idx]),
        "reference_smiles": str(meta.get("SMILES", "")),
        "canonical_match": float(similarities[idx]) >= 0.999999,
    }


def model_artifact_candidates(project_root: Path) -> list[Path]:
    return [
        project_root / "models" / "08_sigmoid_calibrated_ensemble.joblib",
        project_root / "models" / "05_advanced_tuned_candidate.joblib",
    ]


def resolve_artifacts(project_root: Path) -> dict[str, Path | None]:
    candidates = model_artifact_candidates(project_root)
    model_path = next((p for p in candidates if p.is_file()), None)
    return {
        "model": model_path,
        "features": project_root / "data" / "processed" / "phase03" / "03_baseline_features.npz",
        "metadata": project_root / "data" / "processed" / "phase03" / "03_baseline_metadata.csv",
        "raw_data": project_root / "data" / "raw" / "dataset_final.csv",
    }


def rdkit_version() -> str:
    return rdBase.rdkitVersion
