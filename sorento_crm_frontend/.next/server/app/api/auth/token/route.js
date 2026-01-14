/*
 * ATTENTION: An "eval-source-map" devtool has been used.
 * This devtool is neither made for production nor for readable output files.
 * It uses "eval()" calls to create a separate source file with attached SourceMaps in the browser devtools.
 * If you are trying to read the output file, select a different devtool (https://webpack.js.org/configuration/devtool/)
 * or disable the default devtool with "devtool: false".
 * If you are looking for production-ready output files, see mode: "production" (https://webpack.js.org/configuration/mode/).
 */
(() => {
var exports = {};
exports.id = "app/api/auth/token/route";
exports.ids = ["app/api/auth/token/route"];
exports.modules = {

/***/ "(rsc)/./app/api/auth/token/route.ts":
/*!*************************************!*\
  !*** ./app/api/auth/token/route.ts ***!
  \*************************************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

"use strict";
eval("__webpack_require__.r(__webpack_exports__);\n/* harmony export */ __webpack_require__.d(__webpack_exports__, {\n/* harmony export */   GET: () => (/* binding */ GET)\n/* harmony export */ });\n/* harmony import */ var next_server__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! next/server */ \"(rsc)/./node_modules/next/dist/api/server.js\");\n/* harmony import */ var next_auth_jwt__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! next-auth/jwt */ \"(rsc)/./node_modules/next-auth/jwt/index.js\");\n/* harmony import */ var next_auth_jwt__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(next_auth_jwt__WEBPACK_IMPORTED_MODULE_1__);\n/* harmony import */ var jsonwebtoken__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! jsonwebtoken */ \"(rsc)/./node_modules/jsonwebtoken/index.js\");\n/* harmony import */ var jsonwebtoken__WEBPACK_IMPORTED_MODULE_2___default = /*#__PURE__*/__webpack_require__.n(jsonwebtoken__WEBPACK_IMPORTED_MODULE_2__);\n\n\n\n/**\n * API route to get a signed JWT token for FastAPI.\n * NextAuth uses encrypted JWE tokens, so we decode and re-sign as a standard JWT.\n */ async function GET(request) {\n    try {\n        const secret = process.env.NEXTAUTH_SECRET;\n        if (!secret) {\n            return next_server__WEBPACK_IMPORTED_MODULE_0__.NextResponse.json({\n                error: 'NEXTAUTH_SECRET not configured'\n            }, {\n                status: 500\n            });\n        }\n        // Get the decoded token payload from NextAuth (not raw encrypted token)\n        const tokenPayload = await (0,next_auth_jwt__WEBPACK_IMPORTED_MODULE_1__.getToken)({\n            req: request,\n            secret,\n            raw: false // Get decoded payload, not encrypted token\n        });\n        if (!tokenPayload) {\n            return next_server__WEBPACK_IMPORTED_MODULE_0__.NextResponse.json({\n                error: 'No valid token found'\n            }, {\n                status: 401\n            });\n        }\n        // Re-sign as a standard JWT (not encrypted) for FastAPI\n        // FastAPI can decode this with the same secret\n        const signedToken = jsonwebtoken__WEBPACK_IMPORTED_MODULE_2___default().sign({\n            sub: tokenPayload.id || tokenPayload.sub,\n            id: tokenPayload.id,\n            email: tokenPayload.email,\n            name: tokenPayload.name,\n            avatar: tokenPayload.avatar,\n            status: tokenPayload.status,\n            roleId: tokenPayload.roleId,\n            roleName: tokenPayload.roleName\n        }, secret, {\n            algorithm: 'HS256',\n            expiresIn: '24h'\n        });\n        return next_server__WEBPACK_IMPORTED_MODULE_0__.NextResponse.json({\n            token: signedToken\n        });\n    } catch (error) {\n        console.error('Error getting token:', error);\n        return next_server__WEBPACK_IMPORTED_MODULE_0__.NextResponse.json({\n            error: 'Failed to get token'\n        }, {\n            status: 500\n        });\n    }\n}\n//# sourceURL=[module]\n//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiKHJzYykvLi9hcHAvYXBpL2F1dGgvdG9rZW4vcm91dGUudHMiLCJtYXBwaW5ncyI6Ijs7Ozs7Ozs7O0FBQXdEO0FBQ2Y7QUFDVjtBQUUvQjs7O0NBR0MsR0FDTSxlQUFlRyxJQUFJQyxPQUFvQjtJQUM1QyxJQUFJO1FBQ0YsTUFBTUMsU0FBU0MsUUFBUUMsR0FBRyxDQUFDQyxlQUFlO1FBRTFDLElBQUksQ0FBQ0gsUUFBUTtZQUNYLE9BQU9MLHFEQUFZQSxDQUFDUyxJQUFJLENBQ3RCO2dCQUFFQyxPQUFPO1lBQWlDLEdBQzFDO2dCQUFFQyxRQUFRO1lBQUk7UUFFbEI7UUFFQSx3RUFBd0U7UUFDeEUsTUFBTUMsZUFBZSxNQUFNWCx1REFBUUEsQ0FBQztZQUNsQ1ksS0FBS1Q7WUFDTEM7WUFDQVMsS0FBSyxNQUFPLDJDQUEyQztRQUN6RDtRQUVBLElBQUksQ0FBQ0YsY0FBYztZQUNqQixPQUFPWixxREFBWUEsQ0FBQ1MsSUFBSSxDQUN0QjtnQkFBRUMsT0FBTztZQUF1QixHQUNoQztnQkFBRUMsUUFBUTtZQUFJO1FBRWxCO1FBRUEsd0RBQXdEO1FBQ3hELCtDQUErQztRQUMvQyxNQUFNSSxjQUFjYix3REFBUSxDQUMxQjtZQUNFZSxLQUFLTCxhQUFhTSxFQUFFLElBQUlOLGFBQWFLLEdBQUc7WUFDeENDLElBQUlOLGFBQWFNLEVBQUU7WUFDbkJDLE9BQU9QLGFBQWFPLEtBQUs7WUFDekJDLE1BQU1SLGFBQWFRLElBQUk7WUFDdkJDLFFBQVFULGFBQWFTLE1BQU07WUFDM0JWLFFBQVFDLGFBQWFELE1BQU07WUFDM0JXLFFBQVFWLGFBQWFVLE1BQU07WUFDM0JDLFVBQVVYLGFBQWFXLFFBQVE7UUFDakMsR0FDQWxCLFFBQ0E7WUFDRW1CLFdBQVc7WUFDWEMsV0FBVztRQUNiO1FBR0YsT0FBT3pCLHFEQUFZQSxDQUFDUyxJQUFJLENBQUM7WUFBRWlCLE9BQU9YO1FBQVk7SUFDaEQsRUFBRSxPQUFPTCxPQUFPO1FBQ2RpQixRQUFRakIsS0FBSyxDQUFDLHdCQUF3QkE7UUFDdEMsT0FBT1YscURBQVlBLENBQUNTLElBQUksQ0FDdEI7WUFBRUMsT0FBTztRQUFzQixHQUMvQjtZQUFFQyxRQUFRO1FBQUk7SUFFbEI7QUFDRiIsInNvdXJjZXMiOlsiL1VzZXJzL3RlaGpheXNvbi9Eb2N1bWVudHMvZm91bmRyeXgvc29yZW50b19jcm0vc29yZW50b19jcm1fZnJvbnRlbmQvYXBwL2FwaS9hdXRoL3Rva2VuL3JvdXRlLnRzIl0sInNvdXJjZXNDb250ZW50IjpbImltcG9ydCB7IE5leHRSZXF1ZXN0LCBOZXh0UmVzcG9uc2UgfSBmcm9tICduZXh0L3NlcnZlcic7XG5pbXBvcnQgeyBnZXRUb2tlbiB9IGZyb20gJ25leHQtYXV0aC9qd3QnO1xuaW1wb3J0IGp3dCBmcm9tICdqc29ud2VidG9rZW4nO1xuXG4vKipcbiAqIEFQSSByb3V0ZSB0byBnZXQgYSBzaWduZWQgSldUIHRva2VuIGZvciBGYXN0QVBJLlxuICogTmV4dEF1dGggdXNlcyBlbmNyeXB0ZWQgSldFIHRva2Vucywgc28gd2UgZGVjb2RlIGFuZCByZS1zaWduIGFzIGEgc3RhbmRhcmQgSldULlxuICovXG5leHBvcnQgYXN5bmMgZnVuY3Rpb24gR0VUKHJlcXVlc3Q6IE5leHRSZXF1ZXN0KSB7XG4gIHRyeSB7XG4gICAgY29uc3Qgc2VjcmV0ID0gcHJvY2Vzcy5lbnYuTkVYVEFVVEhfU0VDUkVUO1xuICAgIFxuICAgIGlmICghc2VjcmV0KSB7XG4gICAgICByZXR1cm4gTmV4dFJlc3BvbnNlLmpzb24oXG4gICAgICAgIHsgZXJyb3I6ICdORVhUQVVUSF9TRUNSRVQgbm90IGNvbmZpZ3VyZWQnIH0sXG4gICAgICAgIHsgc3RhdHVzOiA1MDAgfVxuICAgICAgKTtcbiAgICB9XG5cbiAgICAvLyBHZXQgdGhlIGRlY29kZWQgdG9rZW4gcGF5bG9hZCBmcm9tIE5leHRBdXRoIChub3QgcmF3IGVuY3J5cHRlZCB0b2tlbilcbiAgICBjb25zdCB0b2tlblBheWxvYWQgPSBhd2FpdCBnZXRUb2tlbih7IFxuICAgICAgcmVxOiByZXF1ZXN0LCBcbiAgICAgIHNlY3JldCxcbiAgICAgIHJhdzogZmFsc2UgIC8vIEdldCBkZWNvZGVkIHBheWxvYWQsIG5vdCBlbmNyeXB0ZWQgdG9rZW5cbiAgICB9KTtcblxuICAgIGlmICghdG9rZW5QYXlsb2FkKSB7XG4gICAgICByZXR1cm4gTmV4dFJlc3BvbnNlLmpzb24oXG4gICAgICAgIHsgZXJyb3I6ICdObyB2YWxpZCB0b2tlbiBmb3VuZCcgfSxcbiAgICAgICAgeyBzdGF0dXM6IDQwMSB9XG4gICAgICApO1xuICAgIH1cblxuICAgIC8vIFJlLXNpZ24gYXMgYSBzdGFuZGFyZCBKV1QgKG5vdCBlbmNyeXB0ZWQpIGZvciBGYXN0QVBJXG4gICAgLy8gRmFzdEFQSSBjYW4gZGVjb2RlIHRoaXMgd2l0aCB0aGUgc2FtZSBzZWNyZXRcbiAgICBjb25zdCBzaWduZWRUb2tlbiA9IGp3dC5zaWduKFxuICAgICAge1xuICAgICAgICBzdWI6IHRva2VuUGF5bG9hZC5pZCB8fCB0b2tlblBheWxvYWQuc3ViLFxuICAgICAgICBpZDogdG9rZW5QYXlsb2FkLmlkLFxuICAgICAgICBlbWFpbDogdG9rZW5QYXlsb2FkLmVtYWlsLFxuICAgICAgICBuYW1lOiB0b2tlblBheWxvYWQubmFtZSxcbiAgICAgICAgYXZhdGFyOiB0b2tlblBheWxvYWQuYXZhdGFyLFxuICAgICAgICBzdGF0dXM6IHRva2VuUGF5bG9hZC5zdGF0dXMsXG4gICAgICAgIHJvbGVJZDogdG9rZW5QYXlsb2FkLnJvbGVJZCxcbiAgICAgICAgcm9sZU5hbWU6IHRva2VuUGF5bG9hZC5yb2xlTmFtZSxcbiAgICAgIH0sXG4gICAgICBzZWNyZXQsXG4gICAgICB7XG4gICAgICAgIGFsZ29yaXRobTogJ0hTMjU2JyxcbiAgICAgICAgZXhwaXJlc0luOiAnMjRoJywgLy8gTWF0Y2ggTmV4dEF1dGggc2Vzc2lvbiBkdXJhdGlvblxuICAgICAgfVxuICAgICk7XG5cbiAgICByZXR1cm4gTmV4dFJlc3BvbnNlLmpzb24oeyB0b2tlbjogc2lnbmVkVG9rZW4gfSk7XG4gIH0gY2F0Y2ggKGVycm9yKSB7XG4gICAgY29uc29sZS5lcnJvcignRXJyb3IgZ2V0dGluZyB0b2tlbjonLCBlcnJvcik7XG4gICAgcmV0dXJuIE5leHRSZXNwb25zZS5qc29uKFxuICAgICAgeyBlcnJvcjogJ0ZhaWxlZCB0byBnZXQgdG9rZW4nIH0sXG4gICAgICB7IHN0YXR1czogNTAwIH1cbiAgICApO1xuICB9XG59XG4iXSwibmFtZXMiOlsiTmV4dFJlc3BvbnNlIiwiZ2V0VG9rZW4iLCJqd3QiLCJHRVQiLCJyZXF1ZXN0Iiwic2VjcmV0IiwicHJvY2VzcyIsImVudiIsIk5FWFRBVVRIX1NFQ1JFVCIsImpzb24iLCJlcnJvciIsInN0YXR1cyIsInRva2VuUGF5bG9hZCIsInJlcSIsInJhdyIsInNpZ25lZFRva2VuIiwic2lnbiIsInN1YiIsImlkIiwiZW1haWwiLCJuYW1lIiwiYXZhdGFyIiwicm9sZUlkIiwicm9sZU5hbWUiLCJhbGdvcml0aG0iLCJleHBpcmVzSW4iLCJ0b2tlbiIsImNvbnNvbGUiXSwiaWdub3JlTGlzdCI6W10sInNvdXJjZVJvb3QiOiIifQ==\n//# sourceURL=webpack-internal:///(rsc)/./app/api/auth/token/route.ts\n");

/***/ }),

/***/ "(rsc)/./node_modules/next/dist/build/webpack/loaders/next-app-loader/index.js?name=app%2Fapi%2Fauth%2Ftoken%2Froute&page=%2Fapi%2Fauth%2Ftoken%2Froute&appPaths=&pagePath=private-next-app-dir%2Fapi%2Fauth%2Ftoken%2Froute.ts&appDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend%2Fapp&pageExtensions=tsx&pageExtensions=ts&pageExtensions=jsx&pageExtensions=js&rootDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend&isDev=true&tsconfigPath=tsconfig.json&basePath=&assetPrefix=&nextConfigOutput=standalone&preferredRegion=&middlewareConfig=e30%3D!":
/*!************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************!*\
  !*** ./node_modules/next/dist/build/webpack/loaders/next-app-loader/index.js?name=app%2Fapi%2Fauth%2Ftoken%2Froute&page=%2Fapi%2Fauth%2Ftoken%2Froute&appPaths=&pagePath=private-next-app-dir%2Fapi%2Fauth%2Ftoken%2Froute.ts&appDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend%2Fapp&pageExtensions=tsx&pageExtensions=ts&pageExtensions=jsx&pageExtensions=js&rootDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend&isDev=true&tsconfigPath=tsconfig.json&basePath=&assetPrefix=&nextConfigOutput=standalone&preferredRegion=&middlewareConfig=e30%3D! ***!
  \************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

"use strict";
eval("__webpack_require__.r(__webpack_exports__);\n/* harmony export */ __webpack_require__.d(__webpack_exports__, {\n/* harmony export */   patchFetch: () => (/* binding */ patchFetch),\n/* harmony export */   routeModule: () => (/* binding */ routeModule),\n/* harmony export */   serverHooks: () => (/* binding */ serverHooks),\n/* harmony export */   workAsyncStorage: () => (/* binding */ workAsyncStorage),\n/* harmony export */   workUnitAsyncStorage: () => (/* binding */ workUnitAsyncStorage)\n/* harmony export */ });\n/* harmony import */ var next_dist_server_route_modules_app_route_module_compiled__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! next/dist/server/route-modules/app-route/module.compiled */ \"(rsc)/./node_modules/next/dist/server/route-modules/app-route/module.compiled.js\");\n/* harmony import */ var next_dist_server_route_modules_app_route_module_compiled__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(next_dist_server_route_modules_app_route_module_compiled__WEBPACK_IMPORTED_MODULE_0__);\n/* harmony import */ var next_dist_server_route_kind__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! next/dist/server/route-kind */ \"(rsc)/./node_modules/next/dist/server/route-kind.js\");\n/* harmony import */ var next_dist_server_lib_patch_fetch__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! next/dist/server/lib/patch-fetch */ \"(rsc)/./node_modules/next/dist/server/lib/patch-fetch.js\");\n/* harmony import */ var next_dist_server_lib_patch_fetch__WEBPACK_IMPORTED_MODULE_2___default = /*#__PURE__*/__webpack_require__.n(next_dist_server_lib_patch_fetch__WEBPACK_IMPORTED_MODULE_2__);\n/* harmony import */ var _Users_tehjayson_Documents_foundryx_sorento_crm_sorento_crm_frontend_app_api_auth_token_route_ts__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! ./app/api/auth/token/route.ts */ \"(rsc)/./app/api/auth/token/route.ts\");\n\n\n\n\n// We inject the nextConfigOutput here so that we can use them in the route\n// module.\nconst nextConfigOutput = \"standalone\"\nconst routeModule = new next_dist_server_route_modules_app_route_module_compiled__WEBPACK_IMPORTED_MODULE_0__.AppRouteRouteModule({\n    definition: {\n        kind: next_dist_server_route_kind__WEBPACK_IMPORTED_MODULE_1__.RouteKind.APP_ROUTE,\n        page: \"/api/auth/token/route\",\n        pathname: \"/api/auth/token\",\n        filename: \"route\",\n        bundlePath: \"app/api/auth/token/route\"\n    },\n    resolvedPagePath: \"/Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_frontend/app/api/auth/token/route.ts\",\n    nextConfigOutput,\n    userland: _Users_tehjayson_Documents_foundryx_sorento_crm_sorento_crm_frontend_app_api_auth_token_route_ts__WEBPACK_IMPORTED_MODULE_3__\n});\n// Pull out the exports that we need to expose from the module. This should\n// be eliminated when we've moved the other routes to the new format. These\n// are used to hook into the route.\nconst { workAsyncStorage, workUnitAsyncStorage, serverHooks } = routeModule;\nfunction patchFetch() {\n    return (0,next_dist_server_lib_patch_fetch__WEBPACK_IMPORTED_MODULE_2__.patchFetch)({\n        workAsyncStorage,\n        workUnitAsyncStorage\n    });\n}\n\n\n//# sourceMappingURL=app-route.js.map//# sourceURL=[module]\n//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiKHJzYykvLi9ub2RlX21vZHVsZXMvbmV4dC9kaXN0L2J1aWxkL3dlYnBhY2svbG9hZGVycy9uZXh0LWFwcC1sb2FkZXIvaW5kZXguanM/bmFtZT1hcHAlMkZhcGklMkZhdXRoJTJGdG9rZW4lMkZyb3V0ZSZwYWdlPSUyRmFwaSUyRmF1dGglMkZ0b2tlbiUyRnJvdXRlJmFwcFBhdGhzPSZwYWdlUGF0aD1wcml2YXRlLW5leHQtYXBwLWRpciUyRmFwaSUyRmF1dGglMkZ0b2tlbiUyRnJvdXRlLnRzJmFwcERpcj0lMkZVc2VycyUyRnRlaGpheXNvbiUyRkRvY3VtZW50cyUyRmZvdW5kcnl4JTJGc29yZW50b19jcm0lMkZzb3JlbnRvX2NybV9mcm9udGVuZCUyRmFwcCZwYWdlRXh0ZW5zaW9ucz10c3gmcGFnZUV4dGVuc2lvbnM9dHMmcGFnZUV4dGVuc2lvbnM9anN4JnBhZ2VFeHRlbnNpb25zPWpzJnJvb3REaXI9JTJGVXNlcnMlMkZ0ZWhqYXlzb24lMkZEb2N1bWVudHMlMkZmb3VuZHJ5eCUyRnNvcmVudG9fY3JtJTJGc29yZW50b19jcm1fZnJvbnRlbmQmaXNEZXY9dHJ1ZSZ0c2NvbmZpZ1BhdGg9dHNjb25maWcuanNvbiZiYXNlUGF0aD0mYXNzZXRQcmVmaXg9Jm5leHRDb25maWdPdXRwdXQ9c3RhbmRhbG9uZSZwcmVmZXJyZWRSZWdpb249Jm1pZGRsZXdhcmVDb25maWc9ZTMwJTNEISIsIm1hcHBpbmdzIjoiOzs7Ozs7Ozs7Ozs7OztBQUErRjtBQUN2QztBQUNxQjtBQUNnRDtBQUM3SDtBQUNBO0FBQ0E7QUFDQSx3QkFBd0IseUdBQW1CO0FBQzNDO0FBQ0EsY0FBYyxrRUFBUztBQUN2QjtBQUNBO0FBQ0E7QUFDQTtBQUNBLEtBQUs7QUFDTDtBQUNBO0FBQ0EsWUFBWTtBQUNaLENBQUM7QUFDRDtBQUNBO0FBQ0E7QUFDQSxRQUFRLHNEQUFzRDtBQUM5RDtBQUNBLFdBQVcsNEVBQVc7QUFDdEI7QUFDQTtBQUNBLEtBQUs7QUFDTDtBQUMwRjs7QUFFMUYiLCJzb3VyY2VzIjpbIiJdLCJzb3VyY2VzQ29udGVudCI6WyJpbXBvcnQgeyBBcHBSb3V0ZVJvdXRlTW9kdWxlIH0gZnJvbSBcIm5leHQvZGlzdC9zZXJ2ZXIvcm91dGUtbW9kdWxlcy9hcHAtcm91dGUvbW9kdWxlLmNvbXBpbGVkXCI7XG5pbXBvcnQgeyBSb3V0ZUtpbmQgfSBmcm9tIFwibmV4dC9kaXN0L3NlcnZlci9yb3V0ZS1raW5kXCI7XG5pbXBvcnQgeyBwYXRjaEZldGNoIGFzIF9wYXRjaEZldGNoIH0gZnJvbSBcIm5leHQvZGlzdC9zZXJ2ZXIvbGliL3BhdGNoLWZldGNoXCI7XG5pbXBvcnQgKiBhcyB1c2VybGFuZCBmcm9tIFwiL1VzZXJzL3RlaGpheXNvbi9Eb2N1bWVudHMvZm91bmRyeXgvc29yZW50b19jcm0vc29yZW50b19jcm1fZnJvbnRlbmQvYXBwL2FwaS9hdXRoL3Rva2VuL3JvdXRlLnRzXCI7XG4vLyBXZSBpbmplY3QgdGhlIG5leHRDb25maWdPdXRwdXQgaGVyZSBzbyB0aGF0IHdlIGNhbiB1c2UgdGhlbSBpbiB0aGUgcm91dGVcbi8vIG1vZHVsZS5cbmNvbnN0IG5leHRDb25maWdPdXRwdXQgPSBcInN0YW5kYWxvbmVcIlxuY29uc3Qgcm91dGVNb2R1bGUgPSBuZXcgQXBwUm91dGVSb3V0ZU1vZHVsZSh7XG4gICAgZGVmaW5pdGlvbjoge1xuICAgICAgICBraW5kOiBSb3V0ZUtpbmQuQVBQX1JPVVRFLFxuICAgICAgICBwYWdlOiBcIi9hcGkvYXV0aC90b2tlbi9yb3V0ZVwiLFxuICAgICAgICBwYXRobmFtZTogXCIvYXBpL2F1dGgvdG9rZW5cIixcbiAgICAgICAgZmlsZW5hbWU6IFwicm91dGVcIixcbiAgICAgICAgYnVuZGxlUGF0aDogXCJhcHAvYXBpL2F1dGgvdG9rZW4vcm91dGVcIlxuICAgIH0sXG4gICAgcmVzb2x2ZWRQYWdlUGF0aDogXCIvVXNlcnMvdGVoamF5c29uL0RvY3VtZW50cy9mb3VuZHJ5eC9zb3JlbnRvX2NybS9zb3JlbnRvX2NybV9mcm9udGVuZC9hcHAvYXBpL2F1dGgvdG9rZW4vcm91dGUudHNcIixcbiAgICBuZXh0Q29uZmlnT3V0cHV0LFxuICAgIHVzZXJsYW5kXG59KTtcbi8vIFB1bGwgb3V0IHRoZSBleHBvcnRzIHRoYXQgd2UgbmVlZCB0byBleHBvc2UgZnJvbSB0aGUgbW9kdWxlLiBUaGlzIHNob3VsZFxuLy8gYmUgZWxpbWluYXRlZCB3aGVuIHdlJ3ZlIG1vdmVkIHRoZSBvdGhlciByb3V0ZXMgdG8gdGhlIG5ldyBmb3JtYXQuIFRoZXNlXG4vLyBhcmUgdXNlZCB0byBob29rIGludG8gdGhlIHJvdXRlLlxuY29uc3QgeyB3b3JrQXN5bmNTdG9yYWdlLCB3b3JrVW5pdEFzeW5jU3RvcmFnZSwgc2VydmVySG9va3MgfSA9IHJvdXRlTW9kdWxlO1xuZnVuY3Rpb24gcGF0Y2hGZXRjaCgpIHtcbiAgICByZXR1cm4gX3BhdGNoRmV0Y2goe1xuICAgICAgICB3b3JrQXN5bmNTdG9yYWdlLFxuICAgICAgICB3b3JrVW5pdEFzeW5jU3RvcmFnZVxuICAgIH0pO1xufVxuZXhwb3J0IHsgcm91dGVNb2R1bGUsIHdvcmtBc3luY1N0b3JhZ2UsIHdvcmtVbml0QXN5bmNTdG9yYWdlLCBzZXJ2ZXJIb29rcywgcGF0Y2hGZXRjaCwgIH07XG5cbi8vIyBzb3VyY2VNYXBwaW5nVVJMPWFwcC1yb3V0ZS5qcy5tYXAiXSwibmFtZXMiOltdLCJpZ25vcmVMaXN0IjpbXSwic291cmNlUm9vdCI6IiJ9\n//# sourceURL=webpack-internal:///(rsc)/./node_modules/next/dist/build/webpack/loaders/next-app-loader/index.js?name=app%2Fapi%2Fauth%2Ftoken%2Froute&page=%2Fapi%2Fauth%2Ftoken%2Froute&appPaths=&pagePath=private-next-app-dir%2Fapi%2Fauth%2Ftoken%2Froute.ts&appDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend%2Fapp&pageExtensions=tsx&pageExtensions=ts&pageExtensions=jsx&pageExtensions=js&rootDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend&isDev=true&tsconfigPath=tsconfig.json&basePath=&assetPrefix=&nextConfigOutput=standalone&preferredRegion=&middlewareConfig=e30%3D!\n");

/***/ }),

/***/ "(rsc)/./node_modules/next/dist/build/webpack/loaders/next-flight-client-entry-loader.js?server=true!":
/*!******************************************************************************************************!*\
  !*** ./node_modules/next/dist/build/webpack/loaders/next-flight-client-entry-loader.js?server=true! ***!
  \******************************************************************************************************/
/***/ (() => {



/***/ }),

/***/ "(ssr)/./node_modules/next/dist/build/webpack/loaders/next-flight-client-entry-loader.js?server=true!":
/*!******************************************************************************************************!*\
  !*** ./node_modules/next/dist/build/webpack/loaders/next-flight-client-entry-loader.js?server=true! ***!
  \******************************************************************************************************/
/***/ (() => {



/***/ }),

/***/ "../app-render/after-task-async-storage.external":
/*!***********************************************************************************!*\
  !*** external "next/dist/server/app-render/after-task-async-storage.external.js" ***!
  \***********************************************************************************/
/***/ ((module) => {

"use strict";
module.exports = require("next/dist/server/app-render/after-task-async-storage.external.js");

/***/ }),

/***/ "../app-render/work-async-storage.external":
/*!*****************************************************************************!*\
  !*** external "next/dist/server/app-render/work-async-storage.external.js" ***!
  \*****************************************************************************/
/***/ ((module) => {

"use strict";
module.exports = require("next/dist/server/app-render/work-async-storage.external.js");

/***/ }),

/***/ "./work-unit-async-storage.external":
/*!**********************************************************************************!*\
  !*** external "next/dist/server/app-render/work-unit-async-storage.external.js" ***!
  \**********************************************************************************/
/***/ ((module) => {

"use strict";
module.exports = require("next/dist/server/app-render/work-unit-async-storage.external.js");

/***/ }),

/***/ "buffer":
/*!*************************!*\
  !*** external "buffer" ***!
  \*************************/
/***/ ((module) => {

"use strict";
module.exports = require("buffer");

/***/ }),

/***/ "crypto":
/*!*************************!*\
  !*** external "crypto" ***!
  \*************************/
/***/ ((module) => {

"use strict";
module.exports = require("crypto");

/***/ }),

/***/ "events":
/*!*************************!*\
  !*** external "events" ***!
  \*************************/
/***/ ((module) => {

"use strict";
module.exports = require("events");

/***/ }),

/***/ "http":
/*!***********************!*\
  !*** external "http" ***!
  \***********************/
/***/ ((module) => {

"use strict";
module.exports = require("http");

/***/ }),

/***/ "https":
/*!************************!*\
  !*** external "https" ***!
  \************************/
/***/ ((module) => {

"use strict";
module.exports = require("https");

/***/ }),

/***/ "next/dist/compiled/next-server/app-page.runtime.dev.js":
/*!*************************************************************************!*\
  !*** external "next/dist/compiled/next-server/app-page.runtime.dev.js" ***!
  \*************************************************************************/
/***/ ((module) => {

"use strict";
module.exports = require("next/dist/compiled/next-server/app-page.runtime.dev.js");

/***/ }),

/***/ "next/dist/compiled/next-server/app-route.runtime.dev.js":
/*!**************************************************************************!*\
  !*** external "next/dist/compiled/next-server/app-route.runtime.dev.js" ***!
  \**************************************************************************/
/***/ ((module) => {

"use strict";
module.exports = require("next/dist/compiled/next-server/app-route.runtime.dev.js");

/***/ }),

/***/ "stream":
/*!*************************!*\
  !*** external "stream" ***!
  \*************************/
/***/ ((module) => {

"use strict";
module.exports = require("stream");

/***/ }),

/***/ "util":
/*!***********************!*\
  !*** external "util" ***!
  \***********************/
/***/ ((module) => {

"use strict";
module.exports = require("util");

/***/ }),

/***/ "zlib":
/*!***********************!*\
  !*** external "zlib" ***!
  \***********************/
/***/ ((module) => {

"use strict";
module.exports = require("zlib");

/***/ })

};
;

// load runtime
var __webpack_require__ = require("../../../../webpack-runtime.js");
__webpack_require__.C(exports);
var __webpack_exec__ = (moduleId) => (__webpack_require__(__webpack_require__.s = moduleId))
var __webpack_exports__ = __webpack_require__.X(0, ["vendor-chunks/next","vendor-chunks/next-auth","vendor-chunks/@babel","vendor-chunks/jose","vendor-chunks/uuid","vendor-chunks/@panva","vendor-chunks/semver","vendor-chunks/jsonwebtoken","vendor-chunks/jws","vendor-chunks/ecdsa-sig-formatter","vendor-chunks/safe-buffer","vendor-chunks/ms","vendor-chunks/lodash.once","vendor-chunks/lodash.isstring","vendor-chunks/lodash.isplainobject","vendor-chunks/lodash.isnumber","vendor-chunks/lodash.isinteger","vendor-chunks/lodash.isboolean","vendor-chunks/lodash.includes","vendor-chunks/jwa","vendor-chunks/buffer-equal-constant-time"], () => (__webpack_exec__("(rsc)/./node_modules/next/dist/build/webpack/loaders/next-app-loader/index.js?name=app%2Fapi%2Fauth%2Ftoken%2Froute&page=%2Fapi%2Fauth%2Ftoken%2Froute&appPaths=&pagePath=private-next-app-dir%2Fapi%2Fauth%2Ftoken%2Froute.ts&appDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend%2Fapp&pageExtensions=tsx&pageExtensions=ts&pageExtensions=jsx&pageExtensions=js&rootDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend&isDev=true&tsconfigPath=tsconfig.json&basePath=&assetPrefix=&nextConfigOutput=standalone&preferredRegion=&middlewareConfig=e30%3D!")));
module.exports = __webpack_exports__;

})();