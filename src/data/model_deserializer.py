# src/data/model_deserializer.py
"""
Puente hacia ``.venv310`` para deserializar modelos de ``trained_models/*.pkl``.

Corren en un **subproceso aislado** con su propio intérprete (Python 3.10,
paquetes pineados EXACTOS de ``requirements_fcst.txt``) en vez de importar
skforecast/xgboost/lightgbm/catboost directamente en el proceso de
Streamlit (Python 3.13): la deserialización de estos .pkl requiere
reproducir casi exactamente el entorno de entrenamiento de SageMaker --
``numpy==2.0.2`` no tiene wheel para Python 3.13, y aun con versiones
"cercanas" aparecen incompatibilidades binarias más adentro (booster de
XGBoost). Ver CLAUDE.md, sección "AWS SageMaker" / Feature
Importance, para el detalle de cómo se llegó a esta arquitectura.

``.venv310/`` es un venv aparte (gitignorado, igual que ``.venv/``) -- no
existe hasta que se crea a mano siguiendo las instrucciones del README. Si
no existe, ``extraer_feature_importance`` devuelve un error explicativo en
vez de romper.

Los ``.pkl`` vienen de la propia pipeline de SageMaker del equipo (no de
terceros/origen público) -- deserializar acá es una excepción deliberada a
la regla general de no deserializar pickles de este bucket (ver
``model_tar_explorer.py``), decidida junto con el usuario.
"""

import json
import os
import subprocess
import tempfile

from src.config.dynamics_config import root_path

VENV310_PYTHON = os.path.join(root_path, ".venv310", "Scripts", "python.exe")
SCRIPT_SUBPROCESO = os.path.join(root_path, "scripts", "feature_importance_subproceso.py")


def venv310_disponible() -> bool:
    return os.path.exists(VENV310_PYTHON)


def extraer_feature_importance(pkl_bytes: bytes, timeout: int = 120) -> dict:
    """Devuelve ``{"ok": True, "regressor": str, "importancias": [...]}`` o
    ``{"ok": False, "error": str}`` -- nunca lanza excepción, para que el
    caller (una página de Streamlit) siempre pueda mostrar un mensaje."""
    if not venv310_disponible():
        return {
            "ok": False,
            "error": (
                "No está creado `.venv310` (Python 3.10 + requirements_fcst.txt) -- "
                "necesario para deserializar modelos de SageMaker. Ver README, sección "
                "\"AWS SageMaker\"."
            ),
        }

    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as tmp:
        tmp.write(pkl_bytes)
        tmp_path = tmp.name

    try:
        resultado = subprocess.run(
            [VENV310_PYTHON, SCRIPT_SUBPROCESO, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timeout ({timeout}s) deserializando el modelo."}
    finally:
        os.unlink(tmp_path)

    salida = resultado.stdout.strip()
    if not salida:
        return {"ok": False, "error": f"El subproceso no devolvió salida. stderr: {resultado.stderr[:500]}"}

    try:
        return json.loads(salida.splitlines()[-1])
    except json.JSONDecodeError:
        return {"ok": False, "error": f"Salida del subproceso no es JSON válido: {salida[:500]}"}
