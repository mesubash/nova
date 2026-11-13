# Transcription accuracy on a real voice (nepali)

Run on 2026-11-13 with `scripts/voice_benchmark.py --set nepali`: 12 phrases read aloud by the developer (MacBook Air M4, built-in microphone), each transcribed by both backends; local Whisper was told the language is `ne`. Text is normalised before comparison (lowercase, no punctuation, numbers unified). Gemini times include any rate-limit waits. Recordings are not included.

| Backend | Word error rate | Character error rate | Exactly right | Median time | Failed |
| --- | --- | --- | --- | --- | --- |
| Gemini | 43.9% | 25.5% | 3 of 12 | 2.46 s | 0 |
| Local (whisper-large-v3-turbo) | 86.2% | 47.2% | 0 of 12 | 1.24 s | 0 |

| # | Phrase | Gemini | Local (whisper-large-v3-turbo) |
| --- | --- | --- | --- |
| 1 | नेपालको राजधानी कहाँ हो? | नेपालको राजधानी कहाँ हो? (✓) | नेपालकराज देनी कहा हो? (75%) |
| 2 | आज मौसम कस्तो छ? | आज मौसम कस्तो छ? (✓) | आज मोसम कोस्टो चा (75%) |
| 3 | पोखरा काठमाडौंबाट कति टाढा छ? | पोखरा काठमाडौं बाट कति टाढा छ ? (40%) | पोखरा कार्पन्डू बाट कोति टाड़ा छो (100%) |
| 4 | राम्रो निद्राको लागि एउटा सुझाव दिनुहोस्। | ramro nindra ko lagi euta sujaav dinuhos (117%) | रम्रो निंड्राकुलागी उटा सुझाव दिनोस् (83%) |
| 5 | सफारी खोल्नुहोस्। | safari खोल्नुस् (100%) | safari kunos (100%) |
| 6 | मेरा नोटहरू देखाउनुहोस्। | मेरो नोट्हरू देखाउनुहोस्। (67%) | मेरा नोट्स अरुद्देकाउनोज (67%) |
| 7 | एउटा नोट सेभ गर्नुहोस्: दूध र रोटी किन्नु। | एउटा नोट सेभ गर्नुहोस्, दूध र ओट्स किन्नु। (12%) | यो तानो छेवगानोष तो त्रो ओो उचिनू (100%) |
| 8 | नोट तीन मेटाउनुहोस्। | Note 3 मिटाउनुहोस्। (67%) | नो तीन विताउनोवस. (67%) |
| 9 | न्युरल नेटवर्क भनेको के हो, सजिलो भाषामा बताउनुहोस्। | Neural network के हो? सजिलो भाषामा बताउनुहोस्। (38%) | निूरल नेट्वर्क के हो सजीलो भासामा बताऊनो अवस्ट (88%) |
| 10 | धन्यवाद, अहिलेलाई यति नै। | धन्यवाद, अहिलेलाई यति नै। (✓) | दन्यवाद, अईलिलाई येति नही (100%) |
| 11 | मेरो meeting कति बजे छ? | मेरो मिटिङ कति बजे छ? (20%) | मेरो मिटिंग काति बाजिशा (80%) |
| 12 | Safari खोल्नुहोस् र GitHub मा जानुहोस्। | सवारी खोल्नुस र डिटममा जानुहोस्। (67%) | सफारी खोनस्रा गीतम माजान होस् (100%) |
