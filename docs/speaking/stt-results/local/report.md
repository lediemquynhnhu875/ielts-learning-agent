# STT benchmark

Reference: recording scripts, NOT verified audio transcripts. Differences may come from the speaker or STT. No ground-truth WER is claimed.

Timings exclude model loading/download. The first inference may include warm-up. CPU batch timings are not production latency.

Pause/filler metrics are inferred from recognized words, not independently verified audio measurements. Repeats count adjacent identical words only. The existing filler heuristic counts every 'like', including ordinary verb/preposition uses; it may miss spellings such as 'hmmm'.

Model loading: 1.853 seconds.

| Sample | Backend | Fillers prompt | Audio (s) | Processing (s) | RTF | Filler count | Pauses | Timestamps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sample-01 | local | False | 23.36 | 5.005 | 0.214 | 0 | 0 | True |
| sample-01 | local | True | 23.36 | 5.524 | 0.236 | 0 | 0 | True |
| sample-02 | local | False | 17.392 | 5.026 | 0.289 | 1 | 2 | True |
| sample-02 | local | True | 17.392 | 5.2 | 0.299 | 1 | 2 | True |
| sample-03 | local | False | 28.265 | 6.417 | 0.227 | 0 | 1 | True |
| sample-03 | local | True | 28.265 | 5.761 | 0.204 | 0 | 1 | True |
| sample-04 | local | False | 22.889 | 5.488 | 0.24 | 0 | 1 | True |
| sample-04 | local | True | 22.889 | 5.656 | 0.247 | 0 | 1 | True |
| sample-05 | local | False | 30.012 | 11.155 | 0.372 | 0 | 3 | True |
| sample-05 | local | True | 30.012 | 20.644 | 0.688 | N/A | N/A | False |
| sample-06 | local | False | 30.524 | 10.296 | 0.337 | 0 | 3 | True |
| sample-06 | local | True | 30.524 | 10.11 | 0.331 | 3 | 5 | True |
| sample-07 | local | False | 34.495 | 10.012 | 0.29 | 0 | 4 | True |
| sample-07 | local | True | 34.495 | 10.204 | 0.296 | 7 | 8 | True |
| sample-08 | local | False | 22.208 | 5.563 | 0.251 | 0 | 1 | True |
| sample-08 | local | True | 22.208 | 5.249 | 0.236 | 0 | 0 | True |
| sample-09 | local | False | 23.743 | 5.056 | 0.213 | 1 | 3 | True |
| sample-09 | local | True | 23.743 | 5.369 | 0.226 | 4 | 4 | True |
| sample-10 | local | False | 28.351 | 5.392 | 0.19 | 0 | 1 | True |
| sample-10 | local | True | 28.351 | 5.236 | 0.185 | 0 | 1 | True |

## sample-01 / local / keep_fillers=False

I am a university student and I study information technology. I usually attend classes in the morning and work on group projects in the afternoon. In my free time, I enjoy listening to music and walking around my neighborhood. These activities help me relax after a busy day.

Script differences:

No differences after case/punctuation normalization.

## sample-01 / local / keep_fillers=True

I am a university student and I study information technology. I usually attend classes in the morning and work on group projects in the afternoon. In my free time, I enjoy listening to music and walking around my neighborhood. These activities help me relax after a busy day.

Script differences:

No differences after case/punctuation normalization.

## sample-02 / local / keep_fillers=False

My brother lives near my university. He goes to work by bus every morning, and he usually finishes at 6. He don't like cooking, so we often eat together. Sometimes he asks me about my classes, but he doesn't understand the subjects I study.

Script differences:

- replace: `live` -> `lives`
- replace: `go` -> `goes`
- replace: `finish` -> `finishes`
- replace: `six` -> `6`
- replace: `ask` -> `asks`
- replace: `understands` -> `understand`

## sample-02 / local / keep_fillers=True

My brother lives near my university. He goes to work by bus every morning, and he usually finishes at 6. He don't like cooking, so we often eat together. Sometimes he asks me about my classes, but he doesn't understand the subjects I study.

Script differences:

- replace: `live` -> `lives`
- replace: `go` -> `goes`
- replace: `finish` -> `finishes`
- replace: `six` -> `6`
- replace: `ask` -> `asks`
- replace: `understands` -> `understand`

## sample-03 / local / keep_fillers=False

Last weekend, I go to a small restaurant with my friends. We order noodles and talk about our exams. After dinner, we walk to a bookstore and I buy a novel. I didn't go home until 10. Yesterday, I read the first chapter and it was quite interesting.

Script differences:

- replace: `went` -> `go`
- replace: `ten` -> `10`
- replace: `readed` -> `read`

## sample-03 / local / keep_fillers=True

Last weekend, I go to a small restaurant with my friends. We order noodles and talk about our exams. After dinner, we walk to a bookstore and I buy a novel. I didn't go home until 10. Yesterday, I read the first chapter and it was quite interesting.

Script differences:

- replace: `went` -> `go`
- replace: `ten` -> `10`
- replace: `readed` -> `read`

## sample-04 / local / keep_fillers=False

There are many students in my class. We have a lot of homework, but our teacher also gives us useful advice. I need more information about the final project. Last week, I bought two new notebooks and a few equipment for recording audio. These things were quite expensive.

Script differences:

- replace: `student` -> `students`
- replace: `advices` -> `advice`
- replace: `informations` -> `information`
- replace: `notebook` -> `notebooks`
- replace: `thing` -> `things`

## sample-04 / local / keep_fillers=True

There are many students in my class. We have a lot of homework, but our teachers also give us useful advice. I need more information about the final project. Last week, I bought two new notebooks and a few equipment for recording audio. These things were quite expensive.

Script differences:

- replace: `student` -> `students`
- replace: `teacher` -> `teachers`
- replace: `gives` -> `give`
- replace: `advices` -> `advice`
- replace: `informations` -> `information`
- replace: `notebook` -> `notebooks`
- replace: `thing` -> `things`

## sample-05 / local / keep_fillers=False

I live in a small apartment near the campus, it takes about 10 minutes to arrive to my classroom. I am interested in learning English because it is useful for my future job. At the evening, I often discuss about my homework with a friend who lives in the same building.

Script differences:

- insert: `` -> `a`
- replace: `ten` -> `10`
- replace: `on` -> `in`

## sample-05 / local / keep_fillers=True

I live in a small apartment near the campus. It takes about 10 minutes to arrive to my classroom. I am interested on learning English because it is useful for my future job. At the evening, I often discuss about my homework with a friend who lives in the same building. I have a friend who lives in the same building. I have a friend who lives in the same building. I have a friend who lives in the same building. I have a friend who lives in the same building. I have a friend who lives in the same building. I have a friend who lives in the same building.

Script differences:

Timestamp extraction failed: boolean index did not match indexed array along axis 0; size of axis is 0 but size of corresponding boolean axis is 1. Retried without word timestamps; fluency metrics unavailable. Processing time includes both attempts.

- insert: `` -> `a`
- replace: `ten` -> `10`
- insert: `` -> `i have a friend who lives in the same building i have a friend who lives in the same building i have a friend who lives in the same building i have a friend who lives in the same building i have a friend who lives in the same building i have a friend who lives in the same building`

## sample-06 / local / keep_fillers=False

I think my favorite place is the library. I go there because it is quiet and I can focus better. Sometimes I just sit near the window and read. I usually stay there for about an hour before going home.

Script differences:

- delete: `um` -> ``
- delete: `uh` -> ``
- delete: `um` -> ``
- delete: `hmm` -> ``
- delete: `uh` -> ``

## sample-06 / local / keep_fillers=True

I think my favorite place is, um, the library. I go there because, um, it is quiet and I can focus better. And sometimes I just sit near the window and read. Um, I usually stay there for about an hour before going home.

Script differences:

- delete: `um` -> ``
- replace: `uh` -> `um`
- replace: `hmm` -> `and`
- replace: `uh` -> `um`

## sample-07 / local / keep_fillers=False

I usually study at home, at home after dinner. My favorite subject is history. Sorry, I mean computer science. Last month, I went there on Tuesday. I bought a book about programming and I finished it in two weeks.

Script differences:

- delete: `i` -> ``
- delete: `monday no on` -> ``
- delete: `a book` -> ``
- delete: `i` -> ``

## sample-07 / local / keep_fillers=True

Uh, I, I, uh, usually study at home, uh, at home, uh, after dinner. My favorite subject is history. Uh, sorry, I mean computer science. Uh, last month, I went there on Monday. No, on Tuesday, I bought a book, a book about programming, and I, uh, I finished it in two weeks.

Script differences:

- insert: `` -> `uh`
- insert: `` -> `uh`
- insert: `` -> `uh`
- insert: `` -> `uh`
- insert: `` -> `uh`
- insert: `` -> `uh`
- insert: `` -> `uh`

## sample-08 / local / keep_fillers=False

Before an exam, I usually make my homework and learn new vocabulary. When I get a good result, I feel very funny and proud. My teacher gives me many knowledge about English. I want to improve my speaking because it can bring me a better world in the future.

Script differences:

- replace: `vocabularies` -> `vocabulary`
- replace: `work` -> `world`

## sample-08 / local / keep_fillers=True

Before an exam, I usually make my homework and learn new vocabularies. When I get a good result, I feel very funny and proud. My teacher gives me many knowledge about English. I want to improve my speaking because it can bring me a better world in the future.

Script differences:

- replace: `work` -> `world`

## sample-09 / local / keep_fillers=False

When I was a child, I don't like speaking English. My parents were very busy so I studied by myself. I watched videos. But I didn't understood much. Now I am more confident. I can explain my opinion more clear than before.

Script differences:

- delete: `uh` -> ``
- replace: `was` -> `were`
- replace: `study` -> `studied`
- delete: `i` -> ``
- replace: `confidence and um` -> `confident`

## sample-09 / local / keep_fillers=True

Um, when I was a child, I don't like speaking English. My parents were very busy, so I studied by myself. I, I watched videos. Um, but I didn't understood much. Now, I am more confident. Um, I can explain my opinion more clear than before.

Script differences:

- replace: `uh` -> `um`
- replace: `was` -> `were`
- replace: `study` -> `studied`
- insert: `` -> `um`
- replace: `confidence and` -> `confident`

## sample-10 / local / keep_fillers=False

I am comfortable speaking English with my classmates. Although I still make mistakes, I want to develop better study habits and learn how technology affects the environment. Last Thursday, I bought 15 notebooks for $50,000. This Thursday, I will buy 13 pens for $30,000.

Script differences:

- replace: `fifteen` -> `15`
- replace: `fifty thousand dong` -> `50 000`
- replace: `thirteen` -> `13`
- replace: `thirty thousand dong` -> `30 000`

## sample-10 / local / keep_fillers=True

I am comfortable speaking English with my classmates. Although I still make mistakes, I want to develop better study habits and learn how technology affects the environment. Last Thursday, I bought 15 notebooks for $50,000. This Thursday, I will buy 13 pens for $30,000.

Script differences:

- replace: `fifteen` -> `15`
- replace: `fifty thousand dong` -> `50 000`
- replace: `thirteen` -> `13`
- replace: `thirty thousand dong` -> `30 000`
