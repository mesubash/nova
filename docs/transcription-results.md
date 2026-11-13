# Transcription accuracy on a real voice

Run on 2026-11-13 with `scripts/voice_benchmark.py`: 15 phrases read aloud by the developer (MacBook Air M4, built-in microphone), each transcribed by both backends. Text is normalised before comparison (lowercase, no punctuation, number words as digits). Recordings are not included.

| Backend | Word error rate | Exactly right | Median time | Failed |
| --- | --- | --- | --- | --- |
| Gemini | 74.6% | 2 of 15 | 6.91 s | 0 |
| Local (whisper-large-v3-turbo) | 110.9% | 0 of 15 | 1.07 s | 0 |

| # | Phrase | Gemini | Local (whisper-large-v3-turbo) |
| --- | --- | --- | --- |
| 1 | What is the capital of Nepal? | का (100%) | So, that's the first one. It's so good. (117%) |
| 2 | How many days are there in a leap year? | Look at the peer. (100%) | Ticep mp. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. Sc. (500%) |
| 3 | How far is Pokhara from Kathmandu? | How do you order from Katmandu? (67%) | for (100%) |
| 4 | Give me one tip for better sleep. | 90 (100%) | Give me one, please. Pro-protective. (57%) |
| 5 | What time is it in London right now? | I'm free to play with the standard right now. (88%) | I'm going to be cooking on them right now. (88%) |
| 6 | Open Safari. | I'm sorry. (100%) | I'm so hard. (150%) |
| 7 | Open Notes. | house (100%) | All right. (100%) |
| 8 | Search my files for invoice. | Foreign boy. (100%) | not my sign for the book (80%) |
| 9 | Save a note: buy oat milk and bread. | Yo, what's good, milk money, rainbow? (88%) | Give a note, bio, nerd, and gold. (62%) |
| 10 | Show my notes. | My nose. (67%) | an old (100%) |
| 11 | Find notes about milk. | I know the word milk (100%) | Find notes about Merit (25%) |
| 12 | Change note two to call my brother on Sunday. | I need to call my brother on Sunday. (33%) | I am not to call my brother on certain angle. (56%) |
| 13 | Delete note three. | delete note three (✓) | And it's not. (100%) |
| 14 | Explain what a neural network is in simple words. | neural networks and simple world (78%) | and what is a neural network in the central world? (67%) |
| 15 | How do I say thank you in Nepali? | How do I say thank you in Nepali? (✓) | How do I see the game like that? (62%) |
