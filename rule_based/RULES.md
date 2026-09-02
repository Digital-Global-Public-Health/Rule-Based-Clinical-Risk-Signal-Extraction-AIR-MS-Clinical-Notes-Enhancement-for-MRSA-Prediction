# Detailed Explanation of each Rule

The rule-based NLP pipeline extracts MRSA risk signals. Each rule defines a risk factor by combining keywords, abbreviations, ICD-10 codes, and (where relevant) drug names into regular expressions. Regular expressions are further employed to capture medications with common suffixes and to account for typographical variants among other things. This document is the detailed reference for [`lexicons/mrsa_risk_factors_v3.csv`](lexicons/mrsa_risk_factors_v3.csv) and covers all **47 entries** contained in that lexicon version, listed alphabetically by name.

For each rule this document lists:
- **Rationale** — why the factor is a plausible MRSA risk signal.
- **Matches** — the keywords, regex, abbreviations, ICD-10 codes, and drug names the rule is built from.
- **Known limitations** — what the pattern does not (or cannot) distinguish.
- **Example matches** — illustrative note snippets the rule is expected to match.
- **False positives** — plausible ways the rule can fire without a true risk signal being present.

Known limitations and false positives below are primarily based on validation-sample results and secondarily derived from the pattern design (keyword/abbreviation ambiguity, missing context). Of the 47 entries, 34 are core clinical risk factors and 13 are auxiliary entries (admission source, gender, and raw lab-value patterns such as `CRP Measurement`) that support the core factors but are not themselves clinical risk signals.

---

## Table of Contents

- [Adm from ED](#adm-from-ed)
- [Advanced Age](#advanced-age)
- [Albumin Measurement](#albumin-measurement)
- [Antibiotic Exposure](#antibiotic-exposure)
- [Bacteremia](#bacteremia)
- [Bone Marrow Transplant](#bone-marrow-transplant)
- [Central Venous Catheter](#central-venous-catheter)
- [Chronic Kidney Disease](#chronic-kidney-disease)
- [Coronary Artery Disease](#coronary-artery-disease)
- [Corticosteroid Use](#corticosteroid-use)
- [CRP Measurement](#crp-measurement)
- [Diabetes Mellitus](#diabetes-mellitus)
- [Difficulty Swallowing](#difficulty-swallowing)
- [Foley Catheter](#foley-catheter)
- [Glucose Measurement](#glucose-measurement)
- [Hematologic Malignancy](#hematologic-malignancy)
- [Hemodialysis](#hemodialysis)
- [Hemoglobin Measurement](#hemoglobin-measurement)
- [HIV/AIDS](#hivaids)
- [ICU Admission](#icu-admission)
- [Immunosuppressant Use](#immunosuppressant-use)
- [Injection Drug Use](#injection-drug-use)
- [INR Measurement](#inr-measurement)
- [Invasive Mechanical Ventilation](#invasive-mechanical-ventilation)
- [Lactate Measurement](#lactate-measurement)
- [LTC/SNF Residence](#ltcsnf-residence)
- [Male Gender](#male-gender)
- [Neutropenia](#neutropenia)
- [Open Wound](#open-wound)
- [Organ Impairment](#organ-impairment)
- [Organ Transplant](#organ-transplant)
- [PCT Measurement](#pct-measurement)
- [Peritoneal Dialysis](#peritoneal-dialysis)
- [Platelet Measurement](#platelet-measurement)
- [Potassium Measurement](#potassium-measurement)
- [Previous Hospital Stay](#previous-hospital-stay)
- [Prior MRSA](#prior-mrsa)
- [Prior Staph](#prior-staph)
- [Receipt of Transfusion](#receipt-of-transfusion)
- [Respiratory Failure](#respiratory-failure)
- [Rheumatic Disease](#rheumatic-disease)
- [Sepsis](#sepsis)
- [Skin or Soft Tissue Infection](#skin-or-soft-tissue-infection)
- [Sodium Measurement](#sodium-measurement)
- [Solid Malignancy](#solid-malignancy)
- [Surgical Procedure](#surgical-procedure)
- [WBC Measurement](#wbc-measurement)

---

## Adm from ED

**Rationale:** Admission via the emergency department signals a more severe presenting condition and exposure to an environment with a high MRSA colonization pressure.

**Matches**
- Keywords: `emergency room`, `emergency department`
- Abbreviations: `ER`, `ED`
- ICD-10 codes: —

**Known limitations:** Mentions of the ED in different settings can lead to false positive matches. The short abbreviations might lead to mismatches, see false positives for an actual example.

**Example matches**
- `Admitted via: Emergency Department`
- `patient came to the ER presenting after near syncopal episode`
- `Primary Service Team: ER`

**False positives**
- `NIFEdipine ER (PROCARDIA XL) 90 mg`

---

## Advanced Age

**Rationale:** Immune function gradually declines with aging, making elderly patients more susceptible to infection. Advanced age is commonly defined as at least 65 years old.

**Matches**
- Keywords: `elderly`, `geriatric`, `nonagenarian`, `octogenarian`, `advanced age`
- Regex: `6[5-9][\s-]?y\.?\s?/?\s?o\.?[mf]?`, `[7-9]\d[\s-]?y\.?\s?/?\s?o\.?[mf]?`, `6[5-9][\s-]?years?[\s-]?old`, `[7-9]\d[\s-]?years?[\s-]?old` — age statements ≥65 combined with a signal word (`years old`, `y.o.`, `yo`)
- ICD-10 codes: —
- Abbreviations: —

**Known limitations:** Advanced age is only recognised if it is explicitly written within the note (e.g. as free text). Other structured data fields containing the patient's age are not considered.

**Example matches**
- `65 years old`
- `78 y.o.`
- `93 yo`
- `85 yoF`
- `elderly patient`

**False positives:** None observed in the validation sample.

---

## Albumin Measurement

**Rationale:** The laboratory measurement for albumin is included as a general indicator of patient vulnerability — low albumin reflects malnutrition and systemic inflammation, both of which increase infection risk.

**Matches**
- Regex: `ALBUMIN(?:,?\s*BLD)?\s*\d+` — matches lab-value mentions such as `ALBUMIN 3.2` or `ALBUMIN, BLD 3.2`
- Abbreviations: —
- ICD-10 codes: —

**Known limitations:** As with all lab-value measurements in this lexicon, the rule matches on the presence of a reported value — it does not check whether that value is outside the normal range. Because only abnormal values are clinically meaningful for MRSA risk, this indicator should be validated against the underlying lab value before further use.

**Example matches**
- `ALBUMIN  2.5`

**False positives:** None observed in the validation sample.

---

## Antibiotic Exposure

**Rationale:** Antibiotic exposure disrupts the normal microbiota, creating an ecological niche for resistant organisms like MRSA. Prior and current antibiotic exposure are included.

**Matches**
- Keywords: `antibiotic`, `antibacterial`, `antimicrobial therapy`, `antibiotics`
- Drug names: `metronidazole`, `sulfamethoxazole`, `trimethoprim`, `rocephin`, `linezolid`, `mupirocin`, `ancef`
- Regex: `ceph\w*`, `cef\w*`, `\w*micin`, `\w*mycin`, `\w*penem`, `\w*floxacin`, `\w*cillin(?<!penicillin)`, `\w*cycline`, `beta[\s-]?lactam`, `quinolone` — matches antibiotic name suffixes (e.g. `ceftriaxone`, `cephalexin`, `vancomycin`, `meropenem`, `ciprofloxacin`, `amoxicillin`)
- Abbreviations: `AMX`, `CIP`, `CLI`, `AZM`, `LEVO`, `SMX-TMP`, `TMP/SMX`, `vanc`, `cef`, `azithro`, `abx`
- ICD-10 codes: —

**Known limitations:** Allergies to antibiotics might be matched even though they do not represent actual exposure. Overlaps with any disease that is typically treated with antibiotics (e.g. MRSA). 

**Example matches**
- `[START ON 14/10/2023] cefTRIAXone (ROCEPHIN)`
- `prescribed oral antibiotics`
- `patient was given vanc/cef/azithro`

**False positives**
- `Allergies: Pcn [Penicillin] amoxicillin`

---

## Bacteremia

**Rationale:** Gives bloodstream infection evidence for any kind of bacteria. The rule searches for specific bacterial infections and general mentions of a bacteremial infection.

**Matches**
- Keywords: `bacterial infection`, `bloodstream infection`, `positive blood culture`, `Serratia`, `e.? coli`, `bacteremia`, `pseudomonas`, `MRSA`
- Abbreviations: `BSI`
- ICD-10 codes: `R78.81`, `A49.9`

**Known limitations:** The lexicon does not include all bacteria — only a small set of specific organisms plus generic bacteremia terms are covered. The bare `MRSA` keyword is broad: it also fires on any MRSA mention that is not a bacteremia diagnosis (e.g. a colonization screen), which can overlap with [Prior MRSA](#prior-mrsa).

**Example matches**
- `MRSA bacteremia`
- `polymicrobial bacteremia on Vancomycin`
- `Patient was found to have positive tracheal sputum cultures for pan-sensitive pseudomonas`

**False positives:** None observed in the validation sample.

---

## Bone Marrow Transplant

**Rationale:** Profound immunosuppression is necessary for transplantation to prevent the recipient's immune system from rejecting the transplanted cells.

**Matches**
- Keywords: `bone marrow transplant`, `stem cell transplant`, `allogeneic transplant`, `autologous transplant`
- Abbreviations: `HSCT`
- ICD-10 codes: `Z94.81`

**Known limitations:** 

**Example matches**
- `s/p allogeneic HSCT for AML`
- `history of autologous stem cell transplant`

**False positives:** None observed in the validation sample.

---

## Central Venous Catheter

**Rationale:** Invasive vascular devices breach the skin barrier and are the primary route for catheter-related bacteremia (CLABSI).

**Matches**
- Keywords: `central line`, `c-line`, `central venous catheter`, `central venous line`, `central venous access catheter`, `port-a-cath`, `tunnelled catheter`, `peripherally inserted central catheter`
- Abbreviations: `CVC`, `PICC`
- ICD-10 codes: —

**Known limitations:** The rule does not distinguish a currently indwelling line from one that has already been removed, so historical, resolved exposures are counted the same as active ones.

**Example matches**
- `PICC line placed for long-term antibiotics`
- `port-a-cath accessed for chemotherapy`

**False positives**
- `CVC removed on day 3`

---

## Chronic Kidney Disease

**Rationale:** Renal failure adversely affects the immune systems and can lead to uremia-associated immune dysfunction. In chronic kidney disease, failing kidney clear less urea, causing blood urea nitrogen (BUN) and creatinine levels to rise. Thus, the BUN measurement is included as an indicator of kidney issues.

**Matches**
- Keywords: `chronic kidney disease`, `chronic renal disease`, `kidney failure`, `impaired kidney function`
- Regex: `BUN\s*>?\s*\d+`, `BUN\s*<?\s*\d+`, `CREAT(?:ININE)?(?:\s*,\s*VEN)?\s*\d+`, `Cr\s*\d+` — matches raw lab-value mentions of BUN, creatinine, or Cr
- Abbreviations: `CKD`
- ICD-10 codes: `N18`

**Known limitations:** As with all lab-value measurements in this lexicon, the rule matches on the presence of a reported BUN or creatinine value — it does not check whether that value is outside the normal range. Because only abnormal values are clinically meaningful for MRSA risk, this indicator should be validated against the underlying lab value before further use.

**Example matches**
- `Patient Active Problem List Diagnosis CKD (chronic kidney disease) stage 4, GFR 15-29 ml/min`

**False positives**
- Any BUN or creatinine lab result is matched, including values within the normal range.

---

## Coronary Artery Disease

**Rationale:** General comorbidity and chronic-disease burden marker rather than a direct infection pathway — included as a frailty proxy.

**Matches**
- Keywords: `coronary artery disease`, `bypass`, `statin therapy`, `beta blockers`, `beta blocker therapy`
- Abbreviations: `CAD`
- ICD-10 codes: `I25`

**Known limitations:** 

**Example matches**
- `diagnosis: CAD`

**False positives:** None observed in the validation sample.

---

## Corticosteroid Use

**Rationale:** Systemic corticosteroids suppress immune function and disrupt the skin barrier. Topical and inhaled forms are included too, since they still cause immune suppression even though they do not breach the skin barrier.

**Matches**
- Keywords: `on steroids`, `steroid therapy`, `corticosteroid`, `chronic steroid use`, `long-term steroid`
- Drug names: `budesonide`, `bethamethasone`, `clobetasol`
- Regex: `\w*sone`, `\w*lone(?<!quinolone)`, `\w*cort\w*`, `\w*onide`, `pred\w*` — matches medication names ending on common corticosteroid suffixes (e.g. `prednisone`, `prednisolone`, `hydrocortisone`, `budesonide`, `fluticasone`)
- Abbreviations: `pred`, `MP`, `dex`
- ICD-10 codes: `Z79.5`

**Known limitations:** The included suffixes might match non-medical terms, see false positive for an example that matches the suffix `-lone`.

**Example matches**
- `resp tx: budesonide/formeterol`

**False positives**
- `Lives with: alone`

---

## CRP Measurement

**Rationale:** The laboratory measurement for C-reactive protein is included as a general indicator for inflammation.

**Matches**
- Regex: `CRP\s*\d+`, `C[\s-]?REACTIVE\s*PROTEIN(?:\s*HS)?\d+`
- Abbreviations: —
- ICD-10 codes: —

**Known limitations:** As with all lab-value measurements in this lexicon, the rule matches on the presence of a reported value — it does not check whether that value is outside the normal range. Because only abnormal values are clinically meaningful for MRSA risk, this indicator should be validated against the underlying lab value before further use.

**Example matches**
- `C REACTIVE PROTEIN HS 281.4`

**False positives:** None observed in the validation sample.

---

## Diabetes Mellitus

**Rationale:** Hyperglycemia impairs neutrophil function and wound healing.

**Matches**
- Keywords: `diabetes mellitus`, `diabetic`, `insulin replacement`
- Drug names: `insulin`, `metformin`, `glipizide`, `glimepiride`, `glyburide`
- Abbreviations: `DM`, `T1D`, `T2D`, `IDDM`, `NIDDM`
- ICD-10 codes: `E10`, `E11`

**Known limitations:** 

**Example matches**
- `HPI (history of the present illness): DM`

**False positives:** None observed in the validation sample.

---

## Difficulty Swallowing

**Rationale:** Difficulty swallowing leads to a raised aspiration risk, an indirect pathway toward pneumonia and MRSA colonisation.

**Matches**
- Keywords: `dysphagia`, `difficulty swallowing`, `limited ability to initiate swallowing`
- Abbreviations: —
- ICD-10 codes: `R13.1`

**Known limitations:** Prior as well as current difficulty swallowing are matched, no distinction in time. 

**Example matches**
- `patient shows limited ability to initiate swallow and spillage`
- `Chief Complaint: Dysphagia`

**False positives:** None observed in the validation sample.

---

## Foley Catheter

**Rationale:** With a breach of the natural skin barrier, a foley catheter represents a direct infection portal and increases CAUTI (catheter-associated urinary tract infection) risk.

**Matches**
- Keywords: `urine catheter`, `foley catheter`, `indwelling catheter`, `catheter-associated UTI`, `foley`
- Abbreviations: `IUC`, `CAUTI`
- ICD-10 codes: —

**Known limitations:** The rule does not distinguish a currently used urine catheter from one that has already been removed, so historical, resolved exposures are counted the same as active ones.

**Example matches**
- `GU: foley in place draining yellow urine`

**False positives:** None observed in the validation sample.

---

## Glucose Measurement

**Rationale:** The laboratory measurement for glucose is included as a general indicator for inflammation.

**Matches**
- Regex: `GLUCOSE(?:-?,?VEN\s*(?:\(?POCT\)?)?)?\s*\d+`
- Abbreviations: —
- ICD-10 codes: —

**Known limitations:** As with all lab-value measurements in this lexicon, the rule matches on the presence of a reported value — it does not check whether that value is outside the normal range. Because only abnormal values are clinically meaningful for MRSA risk, this indicator should be validated against the underlying lab value before further use.

**Example matches**
- `WB GLUCOSE-VEN (POCT) 132`

**False positives:** None observed in the validation sample.

---

## Hematologic Malignancy

**Rationale:** Disease- and treatment-related neutropenia and immune dysregulation.

**Matches**
- Keywords: `hematologic malignancy`, `blood cancer`, `leukemia`, `myeloma`, `lymphoma`
- Abbreviations: `AML`, `CLL`, `CML`, `NHL`
- ICD-10 codes: `C81`–`C85`, `C90`–`C95`

**Known limitations:** This rule does not check if treatment is currently applied.

**Example matches**
- `Medical History: DLBCL (diffuse large B cell lymphoma)`

**False positives:** None observed in the validation sample.

---

## Hemodialysis

**Rationale:** Vascular access for hemodialysis is a recurrent infection portal.

**Matches**
- Keywords: `hemodialysis`, `haemodialysis`, `dialyzer`, `AV fistulas`, `AV graft`, `shunt`
- Abbreviations: `HD`
- ICD-10 codes: `Z99.2`

**Known limitations:** No notable limitations were observed for this rule.

**Example matches**
- `left pubic rami fx plan: hemodialysis`

**False positives**
- `current hemodialysis access: none`

---

## Hemoglobin Measurement

**Rationale:** The laboratory measurement for hemoglobin is included as a general indicator for inflammation or critical condition.

**Matches**
- Regex: `HEMOGLOBIN(?:\s*A1C)?\s*\d+`
- Abbreviations: `Hgb\s*\d+`
- ICD-10 codes: —

**Known limitations:** As with all lab-value measurements in this lexicon, the rule matches on the presence of a reported value — it does not check whether that value is outside the normal range. Because only abnormal values are clinically meaningful for MRSA risk, this indicator should be validated against the underlying lab value before further use.

**Example matches**
- `hemoglobin 9`
- `hemoglobin 7`

**False positives:** None observed in the validation sample.

---

## HIV/AIDS

**Rationale:** CD4-mediated immunodeficiency increases infection risks.

**Matches**
- Keywords: `human immunodeficiency virus`, `HIV`, `AIDS`, `acquired immunodeficiency syndrome`
- Abbreviations: `HIV`, `ART`, `NRTI`, `NNRTI`, `HAART`
- ICD-10 codes: `B20`

**Known limitations:** No notable limitations were observed for this rule.

**Example matches**
- `diagnosis: human immunodeficiency virus`

**False positives**
- `d/c ns aids due to renal damage risk` — refers to NSAIDs (a pain medication class), not AIDS

---

## ICU Admission

**Rationale:** High colonization pressure in the intensive care unit environment increases risk of MRSA colonization. In addition, ICU admission itself is a marker of critical illness.

**Matches**
- Keywords: `intensive[\s-]?care unit` (`intensive-care unit` / `intensive care unit`), `intensive therapy unit`, `intensive treatment unit`, `critical care unit`
- Abbreviations: `ICU`, `ITU`, `MICU`
- ICD-10 codes: —

**Known limitations:** The temporal aspect is not considered.

**Example matches**
- `recommendations: - intensive care unit venous panel to monitor lactate for suspected sepsis`
- `intensive care unit : active lines, drains, and tubes`

**False positives:** None observed in the validation sample.

---

## Immunosuppressant Use

**Rationale:** Anti-rejection and DMARD agents suppress immune function.

**Matches**
- Keywords: `immunosuppressants`, `immunosuppressive drug`, `immunosuppression`, `DMARD`, `biologic therapy`
- Drug names: `azathioprine`, `cyclosporine`, `etanercept`, `methotrexate`, `mycophenolate mofetil`, `tacrolimus`, `adalimumab`, `infliximab`, `sirolimus`
- Abbreviations: `MTX`, `AZA`, `MMF`
- ICD-10 codes: `Z79.60`, `Z79.62`

**Known limitations:** Medication dosage and timing (past vs. current use) are not considered. Shares drug names (tacrolimus, cyclosporine, mycophenolate mofetil, sirolimus) with [Organ Transplant](#organ-transplant), so transplant patients on anti-rejection therapy will also trigger this rule.

**Example matches**
- 

**False positives**
- `suggesting cold agglutinin which would require immunosuppression and plasmapheresis.`

---

## Injection Drug Use

**Rationale:** Skin barrier disruption combined with substance-associated infection risk.

**Matches**
- Keywords: `injection drug use`, `drug injection`, `intravenous drug use`, `intravenous drug abuse`
- Abbreviations: `IDU`, `IVDU`, `PWID`
- ICD-10 codes: `F11`

**Known limitations:** Includes recent and prior injection drug use.

**Example matches**
- `history of polysubstance use - etoh, intravenous drug use`
- `status post intravenous drug use`

**False positives:** None observed in the validation sample.

---

## INR Measurement

**Rationale:** The laboratory measurement for International Normalized Ratio (INR) is included as a general indicator for critical condition.

**Matches**
- Regex: `INR\s*\d+`
- Abbreviations: —
- ICD-10 codes: —

**Known limitations:** As with all lab-value measurements in this lexicon, the rule matches on the presence of a reported value — it does not check whether that value is outside the normal range. Because only abnormal values are clinically meaningful for MRSA risk, this indicator should be validated against the underlying lab value before further use.

**Example matches**
- `INR 1`

**False positives:** None observed in the validation sample.

---

## Invasive Mechanical Ventilation

**Rationale:** Endotracheal intubation bypasses upper airway defenses and carries a risk of ventilator-associated pneumonia. 

**Matches**
- Keywords: `intubated`, `intubation`, `endotracheal tube`
- Regex: `mechanical vent(?:ilation)?`, `invasive vent(?:ilation)?`, `invasive vent(?:ilator)?`, `mechanical vent(?:ilator)?`, `tracheo?tomy` — matches `mechanical`/`invasive` `vent(-ilation)`/`vent(-ilator)` and `tracheotomy`
- Abbreviations: `ETT`, `trach`
- ICD-10 codes: —

**Known limitations:** Overlaps with [Respiratory Failure](#respiratory-failure) via the shared keywords for tracheotomy.

**Example matches**
- `Performed Procedure INTUBATION, ENDOTRACHEAL, EMERGENCY PROCEDURE`
- `s/p trach to trach collar 01/23; Surgical Airway Portex 7 mm Cuffed`
- `history of acute respiratory failure requiring intubation s/p trach and PEG`
- `plan: will continue to monitor patient on mechanical ventilation`

**False positives:** None observed in the validation sample.

---

## Lactate Measurement

**Rationale:** The laboratory measurement for lactate is included as a general indicator for inflammation.

**Matches**
- Regex: `LACTATE(?:-?,?VEN\s*(?:\(?POCT\)?)?)?\s*\d+`
- Abbreviations: `LACT\s*\d+`
- ICD-10 codes: —

**Known limitations:** As with all lab-value measurements in this lexicon, the rule matches on the presence of a reported value — it does not check whether that value is outside the normal range. Because only abnormal values are clinically meaningful for MRSA risk, this indicator should be validated against the underlying lab value before further use.

**Example matches**
- `lactate-ven (poct) 1`
- `LACT 9`

**False positives:** None observed in the validation sample.

---

## LTC/SNF Residence

**Rationale:** High MRSA colonization-pressure environment.

**Matches**
- Keywords: `nursing home`, `long-term care facility`, `skilled nursing facility`, `rehab facility`, `assisted living`, `healthcare facility`
- Abbreviations: `LTCF`, `LTC`, `SNF`, `NH`
- ICD-10 codes: —

**Known limitations:** Planned nursing home residence is not distinguished from previous nursing home residence.

**Example matches**
- `Environment/Residence: Nursing home`
- `presented today from HJC NH for SOB`

**False positives**
- `Is this patient being discharged to a SNF/SAR/LTACH? Yes`

---

## Male Gender

**Rationale:** Included due to observe male predominance in infection susceptibility within the AIR.MS dataset.

**Matches**
- Keywords: `male`
- Abbreviations: —
- ICD-10 codes: —

**Known limitations:** This rule matches any mentions of a person having a male gender (not necessarily related to the patient).

**Example matches**
- `patient is a 65 y.o. male`

**False positives**
- `male partner visited`

---

## Neutropenia

**Rationale:** Severely impaired innate immunity. 

**Matches**
- Keywords: `neutropenia`, `neutropenic`, `ANC low`
- Abbreviations: `GCSF`, `G-CSF`
- ICD-10 codes: `D70`

**Known limitations:** No notable limitations were observed for this rule.

**Example matches**
- `post ob c/b fevers, neutropenic shock`
- `neutropenia with fever`

**False positives:** None observed in the validation sample.

---

## Open Wound

**Rationale:** Direct portal of entry for pathogens. Opioids are included as an indicator, since they are often given after surgery or for pain related to wounds.

**Matches**
- Keywords: `wounds?`, `bleeding`, `purulent discharge`, `opioids?`, `debridement`, `I&D`
- Drug names: `fentanyl`, `morphine`, `methadone`, `buprenorphine`, `meperidine`, `isonipecaine`, `pethidine`, `hydrocodone`, `tapentadol`, `oxycodone`
- Abbreviations: —
- ICD-10 codes: `S01`, `S11`, `S21`, `S31`, `S41`, `S51`, `S61`, `S71`, `S81`, `S91`

**Known limitations:** Opioid medication does not always imply an open wound. The progress/state of the wound is not considered.

**Example matches**
- `#Sacral Decubs/foot wound-wounds do not appear infec ted at this time`
- `addition of multivitamin and ascorbic acid to optimize wound healing`

**False positives**
- `fentanyl 25 mcg/ml in ns 100 ml infusion 25 mcg/hr intravenous`

---

## Organ Impairment

**Rationale:** Critical illness marker that implies physical weakness. The typical assessments Glasgow-Coma-Score (GCS) and SOFA-Score are included as indicators for organ impairment.

**Matches**
- Keywords: `organ impairment`, `organ dysfunction`, `organ failure`, `organ malfunction`, `multiple organ dysfunction syndrome`, `congestive heart failure`, `valvular heart disease`
- Regex: `Glasgow[\s-]?coma[\s-]?scale`, `SOFA[\s-]?score`
- Abbreviations: `MODS`, `CHF`, `GCS`
- ICD-10 codes: `N17`, `N18`, `N19`, `N28.9`, `K72`, `I50`, `G93.4`, `R65.1`

**Known limitations:** The GCS- and SOFA-Score are included as indicators no matter the value.

**Example matches**
- `Patient Active Problem List: CHF (NYHA class III, ACC/AHA stage C)`
- `patient is critically ill with vital organ impairment or failure`

**False positives:** None observed in the validation sample.

---

## Organ Transplant

**Rationale:** Lifelong pharmacologic immunosuppression is necessary to prevent the recipient's immune system from rejecting the transplanted organ.

**Matches**
- Keywords: `organ transplant`, `transplanted organ`, `s/p transplant`, `liver transplant`, `kidney transplant`, `renal transplant`
- Drug names: `tacrolimus`, `cyclosporine`, `mycophenolate mofetil`, `sirolimus`
- Abbreviations: `ATG`
- ICD-10 codes: `Z94.0`–`Z94.5`

**Known limitations:** All four drug names (tacrolimus, cyclosporine, mycophenolate mofetil, sirolimus) are also matched by [Immunosuppressant Use](#immunosuppressant-use), so a single transplant patient will typically trigger both rules for the same underlying medication.

**Example matches**
- `status post renal transplant`
- `solid organ transplant id`

**False positives:** None observed in the validation sample.

---

## PCT Measurement

**Rationale:** The laboratory measurement for Procalcitonin (PCT) is included as a general indicator for inflammation.

**Matches**
- Regex: `PCT\s*\d+`, `Procalcitonin\s*\d+`
- Abbreviations: —
- ICD-10 codes: —

**Known limitations:** As with all lab-value measurements in this lexicon, the rule matches on the presence of a reported value — it does not check whether that value is outside the normal range. Because only abnormal values are clinically meaningful for MRSA risk, this indicator should be validated against the underlying lab value before further use.

**Example matches**
- `procalcitonin 9`

**False positives:** None observed in the validation sample.

---

## Peritoneal Dialysis

**Rationale:** Peritoneal catheter is an infection portal.

**Matches**
- Keywords: `peritoneal dialysis`, `PD catheter`
- Abbreviations: `APD`, `CAPD`
- ICD-10 codes: —

**Known limitations:** The bare abbreviation `PD` is deliberately excluded (only `PD catheter` matches) since `PD` alone is ambiguous (e.g. Parkinson's Disease, postprandial) — this is a precision/recall tradeoff, so shorthand notes using only `PD` are missed. The abbreviation `APD` is also ambigious, it can stand for `afferent pupillary defect`.

**Example matches**
- 

**False positives**
- `apd (relative) afferent pupillary defect lp`

---

## Platelet Measurement

**Rationale:** The laboratory measurement for platelet is included as a general indicator for inflammation or critical condition.

**Matches**
- Regex: `PLATELETS?\s*\d+`
- Abbreviations: —
- ICD-10 codes: —

**Known limitations:** As with all lab-value measurements in this lexicon, the rule matches on the presence of a reported value — it does not check whether that value is outside the normal range. Because only abnormal values are clinically meaningful for MRSA risk, this indicator should be validated against the underlying lab value before further use.

**Example matches**
- `platelet 98 (l)`

**False positives:** None observed in the validation sample.

---

## Potassium Measurement

**Rationale:** The laboratory measurement for potassium is included as a general indicator for inflammation or critical condition.

**Matches**
- Regex: `POTASSIUM(?:\s*,\s*VEN)?\s*\d+`
- Abbreviations: —
- ICD-10 codes: —

**Known limitations:** As with all lab-value measurements in this lexicon, the rule matches on the presence of a reported value — it does not check whether that value is outside the normal range. Because only abnormal values are clinically meaningful for MRSA risk, this indicator should be validated against the underlying lab value before further use.

**Example matches**
- `potassium 4.3`
- `potassium, ven 3.3`

**False positives:** None observed in the validation sample.

---

## Previous Hospital Stay

**Rationale:** Prior healthcare exposure and colonisation pressure.

**Matches**
- Keywords: `previously hospitalized`, `prior admissions?`, `recent hospitalizations?`, `re[\s-]?adm(?:ission)?`, `re[\s-]?admitted`, `recently discharged`, `previous visit to (?:the )?hospital`, `recently hospitalized`, `recently admitted`, `previously admitted`, `recent admissions?`
- Regex: includes different types of spelling
- Abbreviations: —
- ICD-10 codes: —

**Known limitations:** `readmission` and `recently discharged` have no fixed time window in the pattern, so a hospitalization from years ago can match as if it were recent. Surgeries are explicitly not implying a previous hospital stay since surgery is an own risk signal.

**Example matches**
- `chronic elevation of LFT's also present in a previous visit to the hospital`
- `recent admission for aspiration pna`
- `recently admitted to msh for mrsa bacteremia`

**False positives:** None observed in the validation sample.

---

## Prior MRSA

**Rationale:** Strongest single predictor of MRSA — history of colonization or infection.

**Matches**
- Keywords: `history(?:\s*of)?\s*MRSA`, `prior MRSA`, `previously MRSA`, `had MRSA`
- Abbreviations: —
- ICD-10 codes: `Z22.322`, `Z86.14`, `A49.02`

**Known limitations:** Current MRSA diagnosis is not included in this risk signal. The text must match one of the listed terms for a previous infection. See [Bacteremia](#bacteremia), whose bare `MRSA` keyword can overlap with this rule.

**Example matches**
- `prior mrsa bacteremia in dec 2021`

**False positives**
- `pending history mrsa infectious screen`

---

## Prior Staph

**Rationale:** History of Staphylococcus aureus colonization or infection (MSSA).

**Matches**
- Keywords: `SA infection`, `S. Aureus`, `staph infection`, `staphylococcus aureus`
- Abbreviations: `MSSA`, `SA`, `SAB`
- ICD-10 codes: `Z22.321`, `A49.01`

**Known limitations:** Also lists current S. Aureus infection. The abbreviation `SA` collides with the common medical term for oxygen saturation.

**Example matches**
- `clinical labs value: staphylococcus aureus preliminary identification of positive blood broth`
- `d/c is still unknown due to mr sa infection`

**False positives**
- `sa o2: 99%.`

---

## Receipt of Transfusion

**Rationale:** Transfusion of bloods leads transient depression of the immune system (transfusion-related immunomodulation). Furthermore, the necessary vascular access breaches the skin barriers and exposes the patients blood system.

**Matches**
- Keywords: `(?:blood\s+)?transfusions?`, `packed red blood cells`
- Regex: includes plural for (blood) transfusion
- Abbreviations: `PRBC`
- ICD-10 codes: —

**Known limitations:** No temporal check, `candidate for transfusion` also matches.

**Example matches**
- `Responded well to 2 L fluids and 2 units pRBCs`
- `s/p multiple transfusions; Given 2U PRBC`

**False positives:** None observed in the validation sample.

---

## Respiratory Failure

**Rationale:** Critical illness with impaired airway clearance and frequent instrumentation.

**Matches**
- Keywords: `tracheos?tomy`, `resp(?:iratory)? failure`, `ECMO`
- Regex: includes different types of spelling tracheotomy/ tracheostomy and `resp`/`respiratory` failure
- Abbreviations: —
- ICD-10 codes: `J96`, `J95.82`

**Known limitations:** Overlaps with [Invasive Mechanical Ventilation](#invasive-mechanical-ventilation) via the shared keywords for tracheotomy, so the same clinical event can be double-counted across both rules.

**Example matches**
- `history of acute respiratory failure requiring intubation s/p trach and PEG`
- `complication by acute respiratory failure`

**False positives:** None observed in the validation sample.

---

## Rheumatic Disease

**Rationale:** Immunosuppressive therapy for autoimmune/rheumatic disease.

**Matches**
- Keywords: `rheumatism`, `rheumatic disorder`, `rheumatic disease`, `rheumatoid arthritis`, `lupus`, `connective tissue disease`, `erythematosus`
- Abbreviations: `SLE`
- ICD-10 codes: `M79.0`, `M05`, `M06`, `M32`, `M35`

**Known limitations:** No notable limitations were observed for this rule.

**Example matches**
- `foreign body systemic lupus erythematosus`
- `pmh: rheumatoid arthritis`

**False positives:** None observed in the validation sample.

---

## Sepsis

**Rationale:** Systemic infection severity marker.

**Matches**
- Keywords: `sepsis`, `blood poisoning`, `septic shock`
- Abbreviations: —
- ICD-10 codes: `A41`, `R65.2`

**Known limitations:** Does not distinguish a confirmed diagnosis from a suspected one.

**Example matches**
- `received a seven day course of cefepime and metronidazole IV for treatment of sepsis`
- `sepsis likely 2/2 aspiration PNA`

**False positives:** None observed in the validation sample.

---

## Skin or Soft Tissue Infection

**Rationale:** Portal of entry and possible MRSA source.

**Matches**
- Keywords: `skin infection`, `soft-tissue infection`, `cellulitis`, `impetigo`, `erysipelas`, `folliculitis`, `bite wounds?`, `necrotizing fasciitis`, `fournier's gangrene`, `ludwig's angina`, `myonecrosis`, `surgical site infection`, `cutaneous abscess`, `skin abscess`, `subcutaneous abscess`, `soft tissue abscess`, `ecthyma`, `furuncles`, `carbuncles`, `inflamed epidermoid cyst`, `pyomyositis`, `clostridial gas gangrene`, `bacillary angiomatosis`, `infected myositis`
- Abbreviations: `SSTI`, `SSI`
- ICD-10 codes: `L00`–`L05`, `L08`

**Known limitations:** Does not distinguish a confirmed diagnosis from a suspected one.

**Example matches**
- `enhancement throughout the bilateral psoas muscles likely representing an infected myositis`
- `lumbar pyomyositis involving psoas muscle and bilateral paraspinal muscles`

**False positives:** None observed in the validation sample.

---

## Sodium Measurement

**Rationale:** The laboratory measurement for sodium is included as a general indicator for inflammation or critical condition.

**Matches**
- Regex: `SODIUM(?:\s*,\s*VEN)?\s*\d+`, `SODIUM-BLD\s*\d+`
- Abbreviations: —
- ICD-10 codes: —

**Known limitations:** As with all lab-value measurements in this lexicon, the rule matches on the presence of a reported value — it does not check whether that value is outside the normal range. Because only abnormal values are clinically meaningful for MRSA risk, this indicator should be validated against the underlying lab value before further use.

**Example matches**
- `sodium , ven 137`
- `sodium 152`

**False positives:** None observed in the validation sample.

---

## Solid Malignancy

**Rationale:** Tumor- and treatment-related immunosuppression increases susceptibility to and risk of infections.

**Matches**
- Keywords: `solid malignancy`, `solid cancer`, `solid tumor`, `carcinoma`, `sarcoma`, `breast cancer`, `lung cancer`, `colorectal cancer`, `prostate cancer`
- Abbreviations: `SCC`
- ICD-10 codes: `C80`, `C50`, `C61`, `C34`, `C18`, `C25`

**Known limitations:** Limited number of abbreviations for solid malignancies, not every solid cancer is named.

**Example matches**
- `SCC of the right neck`
- `breast cancer , status post lumpectomy`

**False positives**
- `Family History: Cancer Mother`

---

## Surgical Procedure

**Rationale:** Skin integrity breach and possibility for bacteria to enter deep tissues and bloodstream. 

**Matches**
- Keywords: `surgical procedure`, `surgical intervention`, `post-operative`, `knee replacement`, `hip replacement`, `hemiarthroplasty`, `surgery was called`
- Regex: `s/p\s+(?:\w+\s+)?\w*surgery`, `status post\s+(?:\w+\s+)?\w*surgery`, `underwent\s+(?:\w+\s+)?\w*surgery`, `surgery (?:was)?performed`, `\w+ectomy`, `(?!phlebotomy)\w+os?tomy`, `\w+plasty` — includes any word ending on the typical suffixes -o(s)tomy (except for phlebotomy — draining blood from a patient using a needle), -ectomy or -plasty, plus `s/p`/`status post`/`underwent <description> surgery` with the description being one word
- Abbreviations: `UKA`, `TKA`, `TKR`, `THA`, `THR`
- ICD-10 codes: —

**Known limitations:** Specific surgeries with a descirption longer than one word (that are not listed) might not be found, e.g. `status post emergency abdominal surgery`.

**Example matches**
- `s/p lumpectomy`
- `patient received a tracheostomy`
- `s/p R revision TKA 2/13/18`

**False positives**
- `request surgical intervention`

---

## WBC Measurement

**Rationale:** The laboratory measurement for white blood cell (WBC) count is included as a general indicator for inflammation.

**Matches**
- Regex: `WBC:?\s*\d+`, `WHITE BLOOD CELL \d+`
- Abbreviations: —
- ICD-10 codes: —

**Known limitations:** As with all lab-value measurements in this lexicon, the rule matches on the presence of a reported value — it does not check whether that value is outside the normal range. Because only abnormal values are clinically meaningful for MRSA risk, this indicator should be validated against the underlying lab value before further use.

**Example matches**
- `WBC 8`
- `WBC 53`

**False positives:** None observed in the validation sample.
</content>
