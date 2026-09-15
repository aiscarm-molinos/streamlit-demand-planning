# scripts/feature_importance_subproceso.py
"""
Se ejecuta con el Python del entorno ``.venv310`` (Python 3.10 + paquetes
pineados EXACTOS de ``requirements_fcst.txt``, ver README/CLAUDE.md) -- NO
con el Python del venv principal de la app (3.13). Deserializa un .pkl de
``trained_models/`` (joblib.dump de un ``skforecast.ForecasterRecursive``) y
imprime a stdout un único JSON con las feature importances, o un error.

Invocado como subproceso aislado desde ``src/data/model_deserializer.py``
(que corre en el venv principal) -- así el venv de la app nunca necesita
tener instalados skforecast/xgboost/lightgbm/catboost/numpy en la versión
exacta de entrenamiento, que es incompatible con el Python 3.13 de la app
(ver CLAUDE.md, sección "Experimentos SageMaker" / Feature Importance).

Uso: ``python feature_importance_subproceso.py <ruta_al_pkl>``
Salida (stdout, una sola línea JSON):
  {"ok": true, "regressor": "XGBRegressor", "importancias": [{"feature":..., "importance":...}, ...]}
  {"ok": false, "error": "..."}
"""

import json
import sys
import warnings

warnings.filterwarnings("ignore")


def main() -> None:
    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "error": "uso: feature_importance_subproceso.py <ruta_al_pkl>"}))
        return

    pkl_path = sys.argv[1]

    try:
        import joblib
    except ImportError:
        print(json.dumps({"ok": False, "error": "joblib no está instalado en .venv310 -- revisar requirements_fcst.txt"}))
        return

    try:
        obj = joblib.load(pkl_path)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"No se pudo deserializar el .pkl ({type(e).__name__}): {e}"}))
        return

    regresor = getattr(obj, "regressor", obj)
    regresor_tipo = type(regresor).__name__

    try:
        if hasattr(obj, "get_feature_importances"):
            df = obj.get_feature_importances()
        elif hasattr(regresor, "feature_importances_"):
            import pandas as pd

            nombres = getattr(regresor, "feature_names_in_", None)
            valores = regresor.feature_importances_
            if nombres is None:
                nombres = [f"feature_{i}" for i in range(len(valores))]
            df = pd.DataFrame({"feature": list(nombres), "importance": list(valores)})
        else:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": f"El modelo ({type(obj).__name__}, regressor {regresor_tipo}) no expone feature importances.",
                    }
                )
            )
            return
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Error al extraer feature importances ({type(e).__name__}): {e}"}))
        return

    df = df.sort_values("importance", ascending=False)
    print(
        json.dumps(
            {
                "ok": True,
                "regressor": regresor_tipo,
                "skforecast_version": getattr(obj, "skforecast_version", None),
                "importancias": df.to_dict(orient="records"),
            }
        )
    )


if __name__ == "__main__":
    main()
