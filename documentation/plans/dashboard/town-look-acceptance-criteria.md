# UAC: Town look v6 mock (TOWN-LOOK)

Plan: `PLAN-town-look-10nov.md`. Design-only: these criteria judge the mock, not product code.

1. The mock is one static HTML page that loads three.js from a pinned CDN version and opens with no
   build step.
2. Lighting reads as 3D at a glance: buildings cast soft shadows on the ground, and the foot of every
   building is darker than its roof (baked-look AO).
3. The island sits in a sky (gradient + fog), not on a white void; the sea meets a beach.
4. Shops have recognisable roofs, doors and windows; warehouses have barrel roofs; the port has a crane.
5. On load the camera flies in once over about 2.4 s with an ease-out curve; any input skips it.
6. Lorries follow curved roads to the shops of customers with orders due today or overdue (at most 6),
   ease in and out, wait, then return to the depot.
7. Ships leave a wake; a docking ship gets a container lifted off by the crane onto the quay.
8. A new sale plays one delight beat (shop flash, coin arc to the board, counter roll, ground ripple)
   and then returns to calm.
9. With nothing moving (paused, reduced motion, hidden tab) the page stops rendering frames.
10. With `prefers-reduced-motion: reduce` there is no fly-in and nothing drives or bobs; the same data
    is shown statically.
11. The approved card rules from TOWN-V2 still hold: hover tooltip / tap on touch, lightbox popups, tilt
    20-80 deg + zoom + reset, port INCOMING vs LATE, minimal UI.
12. Usable and non-clipped at 1280 px and 375 px.
13. A 15-20 s recording and screenshots at 1280 and 375 sit beside the mock.
