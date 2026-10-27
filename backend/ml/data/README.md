# Data

* `synthetic_india_smoke.csv` – the original 100-row file from this repository. It is **synthetic** (templated phrases).
  It is used only as an out-of-domain smoke test, never for training or headline metrics.
* **EMSCAD is not committed.** Download the Employment Scam Aegean Dataset (`fake_job_postings.csv`, 17,880 rows, 866 fraudulent;
  University of the Aegean, http://emscad.samos.aegean.gr, also on Kaggle "Real or Fake Fake Jobposting Prediction") yourself and check its
  terms before redistributing. Then:

      python -m ml.train --data /path/to/fake_job_postings.csv
      python -m ml.evaluate --data /path/to/fake_job_postings.csv

  `model_metadata.json` records the SHA-256 of the file used so results are reproducible.
