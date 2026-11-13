# Transcription accuracy on a real voice (english)

Run on 2026-11-13 with `scripts/voice_benchmark.py --set english`: 15 phrases read aloud by the developer (MacBook Air M4, built-in microphone), each transcribed by both backends; local Whisper was told the language is `en`. Text is normalised before comparison (lowercase, no punctuation, numbers unified). Gemini times include any rate-limit waits. Recordings are not included.

| Backend | Word error rate | Character error rate | Exactly right | Median time | Failed |
| --- | --- | --- | --- | --- | --- |
| Gemini | 5.6% | 2.3% | 12 of 15 | 2.20 s | 0 |
| Local (whisper-large-v3-turbo) | 9.8% | 3.3% | 9 of 15 | 1.16 s | 0 |

| # | Phrase | Gemini | Local (whisper-large-v3-turbo) |
| --- | --- | --- | --- |
| 1 | What is the capital of Nepal? | What is the capital of Nepal? (✓) | What is the capital of Nepal? (✓) |
| 2 | How many days are there in a leap year? | How many days are there in a leap year? (✓) | How many days are there in a leap year? (✓) |
| 3 | How far is Pokhara from Kathmandu? | How far is Pokhara from Kathmandu? (✓) | How far is Pohara from Kathmandu? (17%) |
| 4 | Give me one tip for better sleep. | Give me one tip for better sleep. (✓) | Give me one tip for better sleep. (✓) |
| 5 | What time is it in London right now? | What time is it in London right now? (✓) | What time is it in London right now? (✓) |
| 6 | Open Safari. | open safari (✓) | Open Safari (✓) |
| 7 | Open Notes. | Open Notes (✓) | Open nodes (50%) |
| 8 | Search my files for invoice. | Show us my files for invoice. (40%) | Search my files for invoice. (✓) |
| 9 | Save a note: buy oat milk and bread. | save a note buy oat milk and bread (✓) | Save a note, buy oatmeal and bread. (25%) |
| 10 | Show my notes. | show my notes (✓) | So my notes (33%) |
| 11 | Find notes about milk. | Find notes about milk. (✓) | find notes about milk (✓) |
| 12 | Change note two to call my brother on Sunday. | Change note to call my brother on Sunday. (11%) | Change note to call my brother on Sunday. (11%) |
| 13 | Delete note three. | Delete node three. (33%) | Delete note three. (✓) |
| 14 | Explain what a neural network is in simple words. | Explain what a neural network is in simple words. (✓) | Explain what a Neuron Network is in simple words. (11%) |
| 15 | How do I say thank you in Nepali? | How do I say thank you in Nepali? (✓) | How do I say thank you in Nepali? (✓) |
