# STT benchmark

Reference: recording scripts, NOT verified audio transcripts. Differences may come from the speaker or STT. No ground-truth WER is claimed.

Timings exclude model loading/download. The first inference may include warm-up. CPU batch timings are not production latency.

Pause/filler metrics are inferred from recognized words, not independently verified audio measurements. Repeats count adjacent identical words only. The existing filler heuristic counts every 'like', including ordinary verb/preposition uses; it may miss spellings such as 'hmmm'.

Model loading: N/A seconds.

| Sample | Backend | Fillers prompt | Audio (s) | Processing (s) | RTF | Filler count | Pauses | Timestamps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sample-01 | groq | False | 23.36 | 2.153 | 0.092 | 0 | 1 | True |
| sample-01 | groq | True | 23.36 | 1.594 | 0.068 | 0 | 0 | True |
| sample-02 | groq | False | 17.392 | 1.597 | 0.092 | 1 | 1 | True |
| sample-02 | groq | True | 17.392 | 1.806 | 0.104 | 1 | 0 | True |
| sample-03 | groq | False | 28.265 | 1.33 | 0.047 | 0 | 1 | True |
| sample-03 | groq | True | 28.265 | 2.235 | 0.079 | 0 | 0 | True |
| sample-04 | groq | False | 22.889 | 2.02 | 0.088 | 0 | 0 | True |
| sample-04 | groq | True | 22.889 | 4.393 | 0.192 | 0 | 0 | True |
| sample-05 | groq | False | 30.012 | 1.415 | 0.047 | 0 | 1 | True |
| sample-05 | groq | True | 30.012 | 1.031 | 0.034 | 0 | 0 | True |
| sample-06 | groq | False | 30.524 | 0.924 | 0.03 | 0 | 3 | True |
| sample-06 | groq | True | 30.524 | 1.075 | 0.035 | 3 | 3 | True |
| sample-07 | groq | False | 34.495 | 2.072 | 0.06 | 0 | 2 | True |
| sample-07 | groq | True | 34.495 | 2.46 | 0.071 | 6 | 0 | True |
| sample-08 | groq | False | 22.208 | 2.03 | 0.091 | 0 | 0 | True |
| sample-08 | groq | True | 22.208 | 1.464 | 0.066 | 0 | 0 | True |
| sample-09 | groq | False | 23.743 | 2.196 | 0.092 | 1 | 0 | True |
| sample-09 | groq | True | 23.743 | 1.855 | 0.078 | 4 | 0 | True |
| sample-10 | groq | False | 28.351 | 1.969 | 0.069 | 0 | 0 | True |
| sample-10 | groq | True | 28.351 | 2.246 | 0.079 | 0 | 0 | True |

## sample-01 / groq / keep_fillers=False

I am a university student and I study information technology. I usually attend classes in the morning and work on group projects in the afternoon. In my free time, I enjoy listening to music and walking around my neighborhood. These activities help me relax after a busy day.

Script differences:

No differences after case/punctuation normalization.

## sample-01 / groq / keep_fillers=True

I am a university student and I study information technology. I usually attend classes in the morning and work on group projects in the afternoon. In my free time, I enjoy listening to music and walking around my neighborhood. These activities help me relax after a busy day.

Script differences:

No differences after case/punctuation normalization.

## sample-02 / groq / keep_fillers=False

My brother lives near my university. He goes to work by bus every morning, and he usually finishes at 6. He don't like cooking, so we often eat together. Sometimes he asks me about my classes, but he doesn't understand the subjects I study.

Script differences:

- replace: `live` -> `lives`
- replace: `go` -> `goes`
- replace: `finish` -> `finishes`
- replace: `six` -> `6`
- replace: `ask` -> `asks`
- replace: `understands` -> `understand`

## sample-02 / groq / keep_fillers=True

My brother lives near my university. He go to work by bus every morning, and he usually finishes at 6. He don't like cooking, so we often eat together. Sometimes he asks me about my classes, but he doesn't understand the subjects I study.

Script differences:

- replace: `live` -> `lives`
- replace: `finish` -> `finishes`
- replace: `six` -> `6`
- replace: `ask` -> `asks`
- replace: `understands` -> `understand`

## sample-03 / groq / keep_fillers=False

Last weekend, I go to a small restaurant with my friends. We order noodles and talk about our exams. After dinner, we walk to a bookstore and I buy a novel. I didn't go home until 10. Yesterday, I read the first chapter and it was quite interesting.

Script differences:

- replace: `went` -> `go`
- replace: `ten` -> `10`
- replace: `readed` -> `read`

## sample-03 / groq / keep_fillers=True

Last weekend, I go to a small restaurant with my friends. We order noodles and talk about our exams. After dinner, we walk to a bookstore and I buy a novel. I didn't go home until 10. Yesterday, I read the first chapter and it was quite interesting.

Script differences:

- replace: `went` -> `go`
- replace: `ten` -> `10`
- replace: `readed` -> `read`

## sample-04 / groq / keep_fillers=False

There are many students in my class. We have a lot of homework, but our teacher also gives us useful advice. I need more information about the final project. Last week, I bought two new notebooks and a few equipment for recording audio. These things were quite expensive.

Script differences:

- replace: `student` -> `students`
- replace: `advices` -> `advice`
- replace: `informations` -> `information`
- replace: `notebook` -> `notebooks`
- replace: `thing` -> `things`

## sample-04 / groq / keep_fillers=True

There are many students in my class. We have a lot of homework, but our teacher also gives us useful advice. I need more information about the final project. Last week, I bought two new notebooks and a few equipment for recording audio. These things were quite expensive.

Script differences:

- replace: `student` -> `students`
- replace: `advices` -> `advice`
- replace: `informations` -> `information`
- replace: `notebook` -> `notebooks`
- replace: `thing` -> `things`

## sample-05 / groq / keep_fillers=False

I live in a small apartment near the campus. It takes about 10 minutes to arrive to my classroom. I am interested in learning English because it is useful for my future job. At the evening, I often discuss about my homework with a friend who lives in the same building.

Script differences:

- insert: `` -> `a`
- replace: `ten` -> `10`
- replace: `on` -> `in`

## sample-05 / groq / keep_fillers=True

I live in a small apartment near the campus. It takes about 10 minutes to arrive to my classroom. I am interested on learning English because it is useful for my future job. At the evening, I often discuss about my homework with a friend who lives in the same building.

Script differences:

- insert: `` -> `a`
- replace: `ten` -> `10`

## sample-06 / groq / keep_fillers=False

I think my favorite place is the library. I go there because it is quiet and I can focus better. Sometimes I just sit near the window and read. I usually stay there for about an hour before going home. Thank you.

Script differences:

- delete: `um` -> ``
- delete: `uh` -> ``
- delete: `um` -> ``
- delete: `hmm` -> ``
- delete: `uh` -> ``
- insert: `` -> `thank you`

## sample-06 / groq / keep_fillers=True

I think my favorite place is, um, the library. I go there because, um, it is quiet and I can focus better. And sometimes I just sit near the window and read. Um, I usually stay there for about an hour before going home. I'm not going to be a good one.

Script differences:

- delete: `um` -> ``
- replace: `uh` -> `um`
- replace: `hmm` -> `and`
- replace: `uh` -> `um`
- insert: `` -> `i'm not going to be a good one`

## sample-07 / groq / keep_fillers=False

I usually study at home after dinner. My favorite subject is history. Sorry, I mean computer science. Last month I went there on Monday No, on Tuesday I bought a book A book about programming And I finished it in two weeks

Script differences:

- delete: `i` -> ``
- delete: `at home` -> ``
- delete: `i` -> ``

## sample-07 / groq / keep_fillers=True

Uh, I, I usually study at home, uh, at home, uh, after dinner. My favorite subject is history. Uh, sorry, I mean computer science. Uh, last month, I went there on Monday. No, on Tuesday, I bought a book, a book about programming, And I, um, I finish it in two weeks.

Script differences:

- insert: `` -> `uh`
- insert: `` -> `uh`
- insert: `` -> `uh`
- insert: `` -> `uh`
- insert: `` -> `uh`
- insert: `` -> `um`
- replace: `finished` -> `finish`

## sample-08 / groq / keep_fillers=False

Before an exam, I usually make my homework and learn new vocabulary. When I get a good result, I feel very funny and proud. My teacher gives me many knowledge about English. I want to improve my speaking because it can bring me a better work in the future.

Script differences:

- replace: `vocabularies` -> `vocabulary`

## sample-08 / groq / keep_fillers=True

Before an exam, I usually make my homework and learn new vocabulary. When I get a good result, I feel very funny and proud. My teacher gives me many knowledge about English. I want to improve my speaking because it can bring me a better work in the future.

Script differences:

- replace: `vocabularies` -> `vocabulary`

## sample-09 / groq / keep_fillers=False

When I was a child, I don't like speaking English. My parents were very busy so I studied by myself. I watched videos. But I didn't understood much. Now I am more confident. I can explain my opinion more clearly than before.

Script differences:

- delete: `uh` -> ``
- replace: `was` -> `were`
- replace: `study` -> `studied`
- delete: `i` -> ``
- replace: `confidence and um` -> `confident`
- replace: `clear` -> `clearly`

## sample-09 / groq / keep_fillers=True

Um, when I was a child, I don't like speaking English. My parents were very busy so I studied by myself. I, I watched videos. Um, but I didn't understood much. Now, I am more confident. Um, I can explain my opinion more clear than before.

Script differences:

- replace: `uh` -> `um`
- replace: `was` -> `were`
- replace: `study` -> `studied`
- insert: `` -> `um`
- replace: `confidence and` -> `confident`

## sample-10 / groq / keep_fillers=False

I'm comfortable speaking English with my classmates. Although I still make mistakes, I want to develop better study habits and learn how technology affects the environment. Last Thursday I bought 15 notebooks for 50,000 don. This Thursday I will buy 13 pens for 30,000 don.

Script differences:

- replace: `i am` -> `i'm`
- replace: `fifteen` -> `15`
- replace: `fifty thousand dong` -> `50 000 don`
- replace: `thirteen` -> `13`
- replace: `thirty thousand dong` -> `30 000 don`

## sample-10 / groq / keep_fillers=True

I'm comfortable speaking English with my classmates. Although I still make mistakes, I want to develop better study habits and learn how technology affects the environment. Last Thursday, I bought 15 notebooks for 50,000 don. This Thursday, I will buy 13 pens for 30,000 don.

Script differences:

- replace: `i am` -> `i'm`
- replace: `fifteen` -> `15`
- replace: `fifty thousand dong` -> `50 000 don`
- replace: `thirteen` -> `13`
- replace: `thirty thousand dong` -> `30 000 don`
