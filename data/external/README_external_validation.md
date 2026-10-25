BeeSafe AI — External validation data instructions

Place a sourced external dataset at external_honeybee_acute.csv. Required columns:
name, SMILES, label, species, endpoint, exposure_route, label_definition, study_id, source_url, independent_of_apisTox, endpoint_compatible

Use only real, traceable records. `label` must be 0/1 using the same acute honeybee label definition as the trained model.
`independent_of_apisTox` and `endpoint_compatible` are manual attestations and must be True only after reviewing the study/source.
`source_url` and `study_id` must be populated. Do not include invented/example labels.
The notebook will exclude exact structure overlap with the ApisTox source records and report sample size/limitations.
A separate dataset with chronic endpoints, another species, or a different LD50 cutoff is NOT directly compatible with this classifier.
