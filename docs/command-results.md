# Nepali voice command results

Run on 2026-11-16 with `gemini-3.5-flash-lite` using `scripts/command_benchmark.py`: 16 commands read aloud by the developer (MacBook Air M4, built-in microphone), transcribed by Gemini in Nepali mode, and sent to the model in a fresh conversation. The typed phrase was also sent, to separate transcription failures from understanding failures. Proposed actions were validated against a test policy and compared with the expected action. **Nothing was executed.** Recordings are not included.

**Spoken:** 9 of 16 correct · **Typed:** 16 of 16 correct · 0 request failed

| # | Phrase | Heard | Spoken → action | Typed → action |
| --- | --- | --- | --- | --- |
| 1 | सफारी खोल्नुहोस्। |  | no speech heard (✗) | Open the app Safari (✓) |
| 2 | Safari खोल्नुहोस्। | Safari kholnu. | Open the app Safari (✓) | Open the app Safari (✓) |
| 3 | नोट्स खोल्नुहोस्। | कन्नौज | text reply (✗) | Open the app Notes (✓) |
| 4 | क्यालेन्डर खोल्नुहोस्। | calendar kholnus | Open the app Calendar (✓) | Open the app Calendar (✓) |
| 5 | क्याल्कुलेटर खोलिदिनुस्। | Calculator खोल्नुहोस्। | Open the app Calculator (✓) | Open the app Calculator (✓) |
| 6 | GitHub मा जानुहोस्। | गीतामा जान्छौ। | text reply (✗) | Open https://github.com in your browser (✓) |
| 7 | YouTube खोल्नुहोस्। | YouTube खोल्नुहोस्। | Open https://www.youtube.com in your browser (✓) | Open https://www.youtube.com in your browser (✓) |
| 8 | Safari खोल्नुहोस् र GitHub मा जानुहोस्। | safari खोल्नुहोस् र यो ट्याबमा जानुहोस् | Open the app Safari (✓) | Open the app Safari (✓) |
| 9 | मेरा नोटहरू देखाउनुहोस्। | मेरो नोटहरू देखाउनुहोस् | Show your recent notes (✓) | Show your recent notes (✓) |
| 10 | एउटा नोट सेभ गर्नुहोस्: दूध र रोटी किन्नु। | Total notes I've got on God knows Rudra. | Find notes containing "Rudra" (✗) | Save a note: "दूध र रोटी किन्नु" (✓) |
| 11 | दूधको बारेमा नोट खोज्नुहोस्। | दूधको बारेमा नोटको नोट | Find notes containing "दूध" (✓) | Find notes containing "दूध" (✓) |
| 12 | नोट तीन मेटाउनुहोस्। | not teen metadata | Search for files named like "teen metadata" in the approved folder (✗) | Delete note #3: "Pay the electricity bill" (✓) |
| 13 | नोट दुई बदल्नुहोस्: आइतबार दाइलाई फोन गर्नु। | Note थ्री बटनमा हो। आइतबार दाइलाई फोन गर्नु। | Change note #3 from "Pay the electricity bill" to "आइतबार दाइलाई फोन गर्नु।" (✗) | Change note #2 from "Call my brother" to "आइतबार दाइलाई फोन गर्नु।" (✓) |
| 14 | मेरो फाइलमा invoice खोज्नुहोस्। | mero file ma boy ko note | Search for files named like "boy" in the approved folder (✗) | Search for files named like "invoice" in the approved folder (✓) |
| 15 | नेपालको राजधानी कहाँ हो? | नेपालको राजधानी कहाँ हो? | text reply (✓) | text reply (✓) |
| 16 | नोट भनेको के हो? | note भनेको के हो? | text reply (✓) | text reply (✓) |
