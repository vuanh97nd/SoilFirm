SOILFIRM PRO USER GUIDE

1. SIGN-IN AND ACCESS
Click Create a trial account and enter your name, email, username and password. Registration requires the server extension. After registration, click Sign in.
Trial allows input sections 1–3 and standard calculations in sections 4–5. Sections 6–10, optimization, batch import/calculation and PDF export require a full license. Admin accounts retain their management access.

2. SECTION 1 — PROJECT
Enter the project name, design stage, work item, station range and section. Set the road category, embankment location and settlement limit according to the project design.

3. SECTION 2 — GEOMETRY
Enter design fill height Htk, equivalent pavement height Hkcad, crest width, side slope, fill unit weight, ground elevation and groundwater conditions. For widening, define the correct side, width and existing embankment soil. Total calculation height Htt includes Htk, Hkcad and settlement compensation Hbl.

4. SECTION 3 — SOIL
Enter layers from top to bottom with layer codes, thicknesses, soil types, unit weights and drainage conditions. Cohesive soil uses Cc/Cs/Pc or an e–logP curve plus Cv versus pressure. Granular soil uses SPT parameters for the selected model. Match the pressure units displayed in the test tables.
Cc, Cs, e0 and Cv use three decimal places; other numeric quantities use two. Display precision does not guarantee equivalent analytical accuracy.

5. SECTION 4 — NATURAL SETTLEMENT
Select the assessment location and time; the default time is zero days. Click ∑ Calculate consolidation settlement to show the table, quick results and chart. The settlement-versus-time action calculates consolidation history. After changing the assessment location, click Calculate again.

6. SECTION 5 — MECHANICAL TREATMENT
Define excavation/replacement, bamboo or cajuput piles and the fill schedule. Enable waiting or surcharge where appropriate. Click Calculate to view results specific to section 5.
Full-license optimization uses a selectable excavation increment, default 0.50 m; default bamboo and cajuput lengths are 3.00 m and 4.00 m. The excavation search range is currently 0–4 m. The first settlement-compliant alternative is selected. This is not cost optimization and does not replace slope stability checks.

7. SECTION 6 — CONSOLIDATION AND DRAINAGE
Choose natural waiting, PVD, sand drains, surcharge or vacuum. Define spacing, pattern, equivalent diameter, treatment depth, drainage cushion and fill stages. Stage heights must increase and finish at Htt. Calculate to view Sc, St, residual settlement and consolidation degree. Review treated-zone and untreated-depth residual settlement separately where relevant.
Time optimization searches for simultaneous compliance with residual settlement and consolidation criteria. Surcharge duration must not duplicate the last stage waiting time.

8. SECTION 7 — CDM
Choose the road/widening scope and TCVN/BS or ALiCC. Define D, s, Lc, stiffness, pile strength, loads, soil beneath the tips and reinforcement. Calculate in the selected method tab. Review settlement, pile stress, foundation bearing capacity and reinforcement together.
The default selectable CDM length increment is 0.50 m. Batch calculation keeps the other saved inputs and increases pile length up to the soil investigation depth, selecting the first passing length. The TCVN/BS optimizer also accepts pile-spacing ranges. ALiCC has its own Lc increment setting.

9. SECTIONS 8–10 — OPTIONS, SUMMARY AND QUANTITIES
Section 8 compares calculated options. Section 9 summarizes current or saved section results. Section 10 calculates quantities using the selected treatment, segment length and geometry. Choose the correct CDM pile-count source: cell-area calculation or CIRCLE entities on the CAD layer.

10. EXCEL AND BATCH CALCULATION
Data must contain THSH and CTDY. Project, design stage and work item are read from THSH!A3, A4 and A5. Layer codes are on row 10; N:AD contains layer thicknesses and AE contains drainage conditions. CTDY parameters are matched by layer code. If present, eCV-P supplies e–P and Cv–P tables with explicitly stated units.
Recalculate and save Excel formulas in Excel or LibreOffice before importing. openpyxl does not evaluate formulas.
Choose section numbers or leave the selection empty for all sections. Set the output folder, up to five priority options, excavation/CDM increments and pile lengths. Empty priorities are skipped. Each section stops at the first passing option.
Export Data writes a copy containing SD/PVD fill-stage results and relevant treatment parameters. Stability factors without a corresponding model are omitted. BTH stores option and section data for quantity calculations. The source workbook is not overwritten.

11. QUICK RESULTS AND CHARTS
Sections 4–7 keep separate calculated results. Quick results and charts stay hidden until Calculate is clicked. Returning to a calculated section restores its results and chart. Input changes invalidate previous results. CDM quick results appear after calculation in the selected method tab.

12. PDF AND LANGUAGE
Choose Vietnamese or English before exporting. Calculate the selected section/method first. Choose Yes in the logo prompt to place the SoilFirm Pro logo at the upper-right page edge, or No to export without the logo. Formulas use MathText for fractions, roots, subscripts and exponents. Install requirements_update.txt. PDF export is unavailable in Trial.

13. SUPPORT
Click “24/7 online support — click here”. Send text and optionally attach PNG/JPEG/WebP images. Images are converted to JPEG and limited to 2 MB after processing. Click View image for the larger image. Messages refresh every ten seconds.
With the server email bridge configured, messages received while admin is offline trigger an email to vuanh97nd@gmail.com. Admin replies above the quoted content, keeping the thread token in the subject. The response is delivered to the corresponding user. Image replies are supported.

14. SAVING AND ERRORS
Save your project as JSON before major input changes. Read calculation messages and complete missing fields. If registration, image chat or email reports an unavailable server feature, update the Worker using SERVER_SETUP.md. Review model assumptions, units and applicable design standards before using calculated results.

15. NOTIFICATIONS AND BACKGROUND MODE
After sign-in, the application checks unread messages every ten seconds. Click View messages in the notification to open the conversation. Close the main window and choose Yes to minimize to the tray, No to exit, or Cancel to keep the window open. The tray menu offers Open SoilFirm Pro and Exit completely. Install pystray/Pillow. The computer must stay on and SoilFirm Pro must already be running and signed in; this feature does not automatically start the application with Windows.
