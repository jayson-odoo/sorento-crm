# Town v2 research: making the town feel alive (10 Nov)

Owner on mock v4: "it doesn't wow me, the things won't move." This is a short survey of what makes a
small 3D town feel alive, with the one technique worth taking from each reference. The motion in mock
v5 (`mock/town-v2-mock-v5.html`) is built from these. tympanus.net and discourse.threejs.org are blocked
by this sandbox's network, so those two entries come from search summaries, not a full read.

## References

| # | Reference | Technique worth taking | Used in v5 |
|---|---|---|---|
| 1 | Zippy Town, a toy city with live traffic, day/night lighting and a scroll-driven camera (three.js forum): https://discourse.threejs.org/t/title-zippy-town-a-toy-city-with-live-traffic-day-night-lighting-and-a-scroll-driven-camera/94955 | Cars follow fixed road paths (a polyline plus distance travelled), not physics. Day/night is a light-colour blend over the hour, not new geometry. | Lorries follow depot -> ring road -> shop paths at constant speed with ease-in/out; time-of-day lerps hemisphere/sun light and the sky gradient. |
| 2 | Bruno Simon, folio-2025 (three.js, CC0 assets): https://github.com/brunosimon/folio-2025 and the 2019 case study https://medium.com/@bruno_simon/bruno-simon-portfolio-case-study-960402cc259b | Everything has a small idle life and appears with a little overshoot; the world reacts to you. | Buildings rise with an ease-out-back stagger on load; shops, the board and the port answer hover. |
| 3 | Mini Metro visual design, GDC 2017 (Jamie Churchman): https://gdcvault.com/play/1024250 and https://gamedeveloper.com/design/video-behind-the-minimalistic-visual-design-of-i-mini-metro-i- | You should see how the network is doing at a glance; motion appears only where it carries state. | Every motion stands for a figure: lorries = to deliver, ships = incoming, glow = bought today, pop = a new invoice. Nothing moves for decoration except trees, water and two flags. |
| 4 | Mini Motorways audio talk (Disasterpeace): https://disasterpeace.com/blog/mini-motorways.talk | Something new is announced once, up front, then becomes part of the ambient background. | A new invoice pops a receipt once and flashes the shop; afterwards the shop just keeps its slow glow. |
| 5 | Townscaper (Oskar Stalberg), interview: https://xraispotlight.substack.com/p/how-to-make-procedural-generation | Small hand-placed details keep a generated scene from feeling sterile. | Flags on the office and the port, a crane that unloads, lorries keeping to one side of the road. |
| 6 | Git City / GitHub City (data -> buildings): https://github.com/lohithb26/git-city and https://awesome.ecosyste.ms/projects/github.com%2Fhonzaap%2Fgithubcity | Building height = volume, lit windows = activity: the data is the architecture. | Already true (shop height = 90-day rank, lit = bought today); v5 adds the breathing glow. |
| 7 | Instanced wind sway in three.js (procedural instanced forest, forum): https://discourse.threejs.org/t/procedural-instanced-forest-high-performance-real-trees/88610 | Sway is a per-instance sine on time with its own phase, so it is cheap and never in sync. | Trees and ships use per-instance sine phases on their instance matrices (14 + 6 instances, no shader needed at this size). |
| 8 | Windland case study (Codrops, low-poly three.js on mobile): https://tympanus.net/codrops/2022/04/25/case-study-windland-an-immersive-three-js-experience/ | Fake it cheaply: low-poly, simple lighting, animate transforms in the render loop. | Faceted water (a 56x8 ring, vertex heights from two sines, flat shading), no shadows, no post-processing. |

## Motion principles applied (Disney's 12, adapted to UI)

Source summary: https://blog.marvelapp.com/disneys-motion-principles-in-designing-interface-animations/ and
https://dribbble.com/stories/2020/07/27/disney-principles-of-animation-ui-interactions

- **Slow in, slow out:** every journey (lorry, ship, crane lift, board count) uses ease-in-out or ease-out;
  nothing starts or stops at full speed.
- **Staggered entrance:** buildings rise about 30 ms apart from the plaza outward, and labels fade in last,
  so the town assembles instead of popping in at once.
- **Anticipation and follow-through:** the receipt pop overshoots a little (ease-out-back) and fades as
  it rises; the shop's glow flashes, then settles.
- **Calm by default:** at most 6 lorries and 6 ships move, one receipt every 7-11 s, one ship docking every
  24 s. Ambient motion uses amplitudes under ~0.15 units, so the eye goes to the meaningful moves.

## Guard rails (same as today, kept)

- 30 fps cap; nothing is drawn and the clock stops while the tab is hidden.
- `prefers-reduced-motion`: no motion at all (the static v4 town), as today's page already decides.
- A Pause / Play icon button beside zoom and reset (WCAG 2.2.2: moving content that lasts more than 5 s
  needs a pause), remembered per viewer.
- Mock v5 measures 34-36 draw calls with all motion on, under the 100 budget in the original plan.
