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
exports.id = "app/api/auth/[...nextauth]/route";
exports.ids = ["app/api/auth/[...nextauth]/route"];
exports.modules = {

/***/ "(rsc)/./app/api/auth/[...nextauth]/auth-options.ts":
/*!****************************************************!*\
  !*** ./app/api/auth/[...nextauth]/auth-options.ts ***!
  \****************************************************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

"use strict";
eval("__webpack_require__.r(__webpack_exports__);\n/* harmony export */ __webpack_require__.d(__webpack_exports__, {\n/* harmony export */   \"default\": () => (__WEBPACK_DEFAULT_EXPORT__)\n/* harmony export */ });\n/* harmony import */ var _next_auth_prisma_adapter__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @next-auth/prisma-adapter */ \"(rsc)/./node_modules/@next-auth/prisma-adapter/dist/index.js\");\n/* harmony import */ var bcrypt__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! bcrypt */ \"bcrypt\");\n/* harmony import */ var bcrypt__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(bcrypt__WEBPACK_IMPORTED_MODULE_1__);\n/* harmony import */ var next_auth_providers_credentials__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! next-auth/providers/credentials */ \"(rsc)/./node_modules/next-auth/providers/credentials.js\");\n/* harmony import */ var next_auth_providers_google__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! next-auth/providers/google */ \"(rsc)/./node_modules/next-auth/providers/google.js\");\n/* harmony import */ var _lib_prisma__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! @/lib/prisma */ \"(rsc)/./lib/prisma.ts\");\n\n\n\n\n\nconst authOptions = {\n    adapter: (0,_next_auth_prisma_adapter__WEBPACK_IMPORTED_MODULE_0__.PrismaAdapter)(_lib_prisma__WEBPACK_IMPORTED_MODULE_4__[\"default\"]),\n    providers: [\n        (0,next_auth_providers_credentials__WEBPACK_IMPORTED_MODULE_2__[\"default\"])({\n            name: 'Credentials',\n            credentials: {\n                email: {\n                    label: 'Email',\n                    type: 'text'\n                },\n                password: {\n                    label: 'Password',\n                    type: 'password'\n                },\n                rememberMe: {\n                    label: 'Remember me',\n                    type: 'boolean'\n                }\n            },\n            async authorize (credentials) {\n                if (!credentials || !credentials.email || !credentials.password) {\n                    throw new Error(JSON.stringify({\n                        code: 400,\n                        message: 'Please enter both email and password.'\n                    }));\n                }\n                const user = await _lib_prisma__WEBPACK_IMPORTED_MODULE_4__[\"default\"].user.findUnique({\n                    where: {\n                        email: credentials.email\n                    }\n                });\n                if (!user) {\n                    throw new Error(JSON.stringify({\n                        code: 404,\n                        message: 'User not found. Please register first.'\n                    }));\n                }\n                const isPasswordValid = await bcrypt__WEBPACK_IMPORTED_MODULE_1___default().compare(credentials.password, user.password || '');\n                if (!isPasswordValid) {\n                    throw new Error(JSON.stringify({\n                        code: 401,\n                        message: 'Invalid credentials. Incorrect password.'\n                    }));\n                }\n                if (user.status !== 'ACTIVE') {\n                    throw new Error(JSON.stringify({\n                        code: 403,\n                        message: 'Account not activated. Please verify your email.'\n                    }));\n                }\n                // Update `lastSignInAt` field\n                await _lib_prisma__WEBPACK_IMPORTED_MODULE_4__[\"default\"].user.update({\n                    where: {\n                        id: user.id\n                    },\n                    data: {\n                        lastSignInAt: new Date()\n                    }\n                });\n                return {\n                    id: user.id,\n                    status: user.status,\n                    email: user.email,\n                    name: user.name || 'Anonymous',\n                    roleId: user.roleId,\n                    avatar: user.avatar\n                };\n            }\n        }),\n        (0,next_auth_providers_google__WEBPACK_IMPORTED_MODULE_3__[\"default\"])({\n            clientId: process.env.GOOGLE_CLIENT_ID,\n            clientSecret: process.env.GOOGLE_CLIENT_SECRET,\n            allowDangerousEmailAccountLinking: true,\n            async profile (profile) {\n                const existingUser = await _lib_prisma__WEBPACK_IMPORTED_MODULE_4__[\"default\"].user.findUnique({\n                    where: {\n                        email: profile.email\n                    },\n                    include: {\n                        role: {\n                            select: {\n                                id: true,\n                                name: true\n                            }\n                        }\n                    }\n                });\n                if (existingUser) {\n                    // Update `lastSignInAt` field for existing users\n                    await _lib_prisma__WEBPACK_IMPORTED_MODULE_4__[\"default\"].user.update({\n                        where: {\n                            id: existingUser.id\n                        },\n                        data: {\n                            name: profile.name,\n                            avatar: profile.picture || null,\n                            lastSignInAt: new Date()\n                        }\n                    });\n                    return {\n                        id: existingUser.id,\n                        email: existingUser.email,\n                        name: existingUser.name || 'Anonymous',\n                        status: existingUser.status,\n                        roleId: existingUser.roleId,\n                        roleName: existingUser.role.name,\n                        avatar: existingUser.avatar\n                    };\n                }\n                const defaultRole = await _lib_prisma__WEBPACK_IMPORTED_MODULE_4__[\"default\"].userRole.findFirst({\n                    where: {\n                        isDefault: true\n                    }\n                });\n                if (!defaultRole) {\n                    throw new Error('Default role not found. Unable to create a new user.');\n                }\n                // Create a new user and account\n                const newUser = await _lib_prisma__WEBPACK_IMPORTED_MODULE_4__[\"default\"].user.create({\n                    data: {\n                        email: profile.email,\n                        name: profile.name,\n                        password: '',\n                        avatar: profile.picture || null,\n                        emailVerifiedAt: new Date(),\n                        roleId: defaultRole.id,\n                        status: 'ACTIVE'\n                    }\n                });\n                return {\n                    id: newUser.id,\n                    email: newUser.email,\n                    name: newUser.name || 'Anonymous',\n                    status: newUser.status,\n                    avatar: newUser.avatar,\n                    roleId: newUser.roleId,\n                    roleName: defaultRole.name\n                };\n            }\n        })\n    ],\n    session: {\n        strategy: 'jwt',\n        maxAge: 24 * 60 * 60\n    },\n    callbacks: {\n        async jwt ({ token, user, session, trigger }) {\n            if (trigger === 'update' && session?.user) {\n                token = session.user;\n            } else {\n                if (user && user.roleId) {\n                    const role = await _lib_prisma__WEBPACK_IMPORTED_MODULE_4__[\"default\"].userRole.findUnique({\n                        where: {\n                            id: user.roleId\n                        }\n                    });\n                    token.id = user.id || token.sub;\n                    token.email = user.email;\n                    token.name = user.name;\n                    token.avatar = user.avatar;\n                    token.status = user.status;\n                    token.roleId = user.roleId;\n                    token.roleName = role?.name;\n                }\n            }\n            return token;\n        },\n        async session ({ session, token }) {\n            if (session.user) {\n                session.user.id = token.id;\n                session.user.email = token.email;\n                session.user.name = token.name;\n                session.user.avatar = token.avatar;\n                session.user.status = token.status;\n                session.user.roleId = token.roleId;\n                session.user.roleName = token.roleName;\n            }\n            return session;\n        }\n    },\n    pages: {\n        signIn: '/signin'\n    }\n};\n/* harmony default export */ const __WEBPACK_DEFAULT_EXPORT__ = (authOptions);\n//# sourceURL=[module]\n//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiKHJzYykvLi9hcHAvYXBpL2F1dGgvWy4uLm5leHRhdXRoXS9hdXRoLW9wdGlvbnMudHMiLCJtYXBwaW5ncyI6Ijs7Ozs7Ozs7OztBQUEwRDtBQUM5QjtBQUdzQztBQUNWO0FBQ3RCO0FBRWxDLE1BQU1LLGNBQStCO0lBQ25DQyxTQUFTTix3RUFBYUEsQ0FBQ0ksbURBQU1BO0lBQzdCRyxXQUFXO1FBQ1RMLDJFQUFtQkEsQ0FBQztZQUNsQk0sTUFBTTtZQUNOQyxhQUFhO2dCQUNYQyxPQUFPO29CQUFFQyxPQUFPO29CQUFTQyxNQUFNO2dCQUFPO2dCQUN0Q0MsVUFBVTtvQkFBRUYsT0FBTztvQkFBWUMsTUFBTTtnQkFBVztnQkFDaERFLFlBQVk7b0JBQUVILE9BQU87b0JBQWVDLE1BQU07Z0JBQVU7WUFDdEQ7WUFDQSxNQUFNRyxXQUFVTixXQUFXO2dCQUN6QixJQUFJLENBQUNBLGVBQWUsQ0FBQ0EsWUFBWUMsS0FBSyxJQUFJLENBQUNELFlBQVlJLFFBQVEsRUFBRTtvQkFDL0QsTUFBTSxJQUFJRyxNQUNSQyxLQUFLQyxTQUFTLENBQUM7d0JBQ2JDLE1BQU07d0JBQ05DLFNBQVM7b0JBQ1g7Z0JBRUo7Z0JBRUEsTUFBTUMsT0FBTyxNQUFNakIsbURBQU1BLENBQUNpQixJQUFJLENBQUNDLFVBQVUsQ0FBQztvQkFDeENDLE9BQU87d0JBQUViLE9BQU9ELFlBQVlDLEtBQUs7b0JBQUM7Z0JBQ3BDO2dCQUVBLElBQUksQ0FBQ1csTUFBTTtvQkFDVCxNQUFNLElBQUlMLE1BQ1JDLEtBQUtDLFNBQVMsQ0FBQzt3QkFDYkMsTUFBTTt3QkFDTkMsU0FBUztvQkFDWDtnQkFFSjtnQkFFQSxNQUFNSSxrQkFBa0IsTUFBTXZCLHFEQUFjLENBQzFDUSxZQUFZSSxRQUFRLEVBQ3BCUSxLQUFLUixRQUFRLElBQUk7Z0JBR25CLElBQUksQ0FBQ1csaUJBQWlCO29CQUNwQixNQUFNLElBQUlSLE1BQ1JDLEtBQUtDLFNBQVMsQ0FBQzt3QkFDYkMsTUFBTTt3QkFDTkMsU0FBUztvQkFD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bEMsSUFBSSxDQUFDYixJQUFJLEdBQUdvRCxNQUFNcEQsSUFBSTtnQkFDOUIrQyxRQUFRbEMsSUFBSSxDQUFDWSxNQUFNLEdBQUcyQixNQUFNM0IsTUFBTTtnQkFDbENzQixRQUFRbEMsSUFBSSxDQUFDSyxNQUFNLEdBQUdrQyxNQUFNbEMsTUFBTTtnQkFDbEM2QixRQUFRbEMsSUFBSSxDQUFDVyxNQUFNLEdBQUc0QixNQUFNNUIsTUFBTTtnQkFDbEN1QixRQUFRbEMsSUFBSSxDQUFDMEIsUUFBUSxHQUFHYSxNQUFNYixRQUFRO1lBQ3hDO1lBQ0EsT0FBT1E7UUFDVDtJQUNGO0lBQ0FRLE9BQU87UUFDTEMsUUFBUTtJQUNWO0FBQ0Y7QUFFQSxpRUFBZTNELFdBQVdBLEVBQUMiLCJzb3VyY2VzIjpbIi9Vc2Vycy90ZWhqYXlzb24vRG9jdW1lbnRzL2ZvdW5kcnl4L3NvcmVudG9fY3JtL3NvcmVudG9fY3JtX2Zyb250ZW5kL2FwcC9hcGkvYXV0aC9bLi4ubmV4dGF1dGhdL2F1dGgtb3B0aW9ucy50cyJdLCJzb3VyY2VzQ29udGVudCI6WyJpbXBvcnQgeyBQcmlzbWFBZGFwdGVyIH0gZnJvbSAnQG5leHQtYXV0aC9wcmlzbWEtYWRhcHRlcic7XG5pbXBvcnQgYmNyeXB0IGZyb20gJ2JjcnlwdCc7XG5pbXBvcnQgeyBOZXh0QXV0aE9wdGlvbnMsIFNlc3Npb24sIFVzZXIgfSBmcm9tICduZXh0LWF1dGgnO1xuaW1wb3J0IHsgSldUIH0gZnJvbSAnbmV4dC1hdXRoL2p3dCc7XG5pbXBvcnQgQ3JlZGVudGlhbHNQcm92aWRlciBmcm9tICduZXh0LWF1dGgvcHJvdmlkZXJzL2NyZWRlbnRpYWxzJztcbmltcG9ydCBHb29nbGVQcm92aWRlciBmcm9tICduZXh0LWF1dGgvcHJvdmlkZXJzL2dvb2dsZSc7XG5pbXBvcnQgcHJpc21hIGZyb20gJ0AvbGliL3ByaXNtYSc7XG5cbmNvbnN0IGF1dGhPcHRpb25zOiBOZXh0QXV0aE9wdGlvbnMgPSB7XG4gIGFkYXB0ZXI6IFByaXNtYUFkYXB0ZXIocHJpc21hKSxcbiAgcHJvdmlkZXJzOiBbXG4gICAgQ3JlZGVudGlhbHNQcm92aWRlcih7XG4gICAgICBuYW1lOiAnQ3JlZGVudGlhbHMnLFxuICAgICAgY3JlZGVudGlhbHM6IHtcbiAgICAgICAgZW1haWw6IHsgbGFiZWw6ICdFbWFpbCcsIHR5cGU6ICd0ZXh0JyB9LFxuICAgICAgICBwYXNzd29yZDogeyBsYWJlbDogJ1Bhc3N3b3JkJywgdHlwZTogJ3Bhc3N3b3JkJyB9LFxuICAgICAgICByZW1lbWJlck1lOiB7IGxhYmVsOiAnUmVtZW1iZXIgbWUnLCB0eXBlOiAnYm9vbGVhbicgfSxcbiAgICAgIH0sXG4gICAgICBhc3luYyBhdXRob3JpemUoY3JlZGVudGlhbHMpIHtcbiAgICAgICAgaWYgKCFjcmVkZW50aWFscyB8fCAhY3JlZGVudGlhbHMuZW1haWwgfHwgIWNyZWRlbnRpYWxzLnBhc3N3b3JkKSB7XG4gICAgICAgICAgdGhyb3cgbmV3IEVycm9yKFxuICAgICAgICAgICAgSlNPTi5zdHJpbmdpZnkoe1xuICAgICAgICAgICAgICBjb2RlOiA0MDAsXG4gICAgICAgICAgICAgIG1lc3NhZ2U6ICdQbGVhc2UgZW50ZXIgYm90aCBlbWFpbCBhbmQgcGFzc3dvcmQuJyxcbiAgICAgICAgICAgIH0pLFxuICAgICAgICAgICk7XG4gICAgICAgIH1cblxuICAgICAgICBjb25zdCB1c2VyID0gYXdhaXQgcHJpc21hLnVzZXIuZmluZFVuaXF1ZSh7XG4gICAgICAgICAgd2hlcmU6IHsgZW1haWw6IGNyZWRlbnRpYWxzLmVtYWlsIH0sXG4gICAgICAgIH0pO1xuXG4gICAgICAgIGlmICghdXNlcikge1xuICAgICAgICAgIHRocm93IG5ldyBFcnJvcihcbiAgICAgICAgICAgIEpTT04uc3RyaW5naWZ5KHtcbiAgICAgICAgICAgICAgY29kZTogNDA0LFxuICAgICAgICAgICAgICBtZXNzYWdlOiAnVXNlciBub3QgZm91bmQuIFBsZWFzZSByZWdpc3RlciBmaXJzdC4nLFxuICAgICAgICAgICAgfSksXG4gICAgICAgICAgKTtcbiAgICAgICAgfVxuXG4gICAgICAgIGNvbnN0IGlzUGFzc3dvcmRWYWxpZCA9IGF3YWl0IGJjcnlwdC5jb21wYXJlKFxuICAgICAgICAgIGNyZWRlbnRpYWxzLnBhc3N3b3JkLFxuICAgICAgICAgIHVzZXIucGFzc3dvcmQgfHwgJycsXG4gICAgICAgICk7XG5cbiAgICAgICAgaWYgKCFpc1Bhc3N3b3JkVmFsaWQpIHtcbiAgICAgICAgICB0aHJvdyBuZXcgRXJyb3IoXG4gICAgICAgICAgICBKU09OLnN0cmluZ2lmeSh7XG4gICAgICAgICAgICAgIGNvZGU6IDQwMSxcbiAgICAgICAgICAgICAgbWVzc2FnZTogJ0ludmFsaWQgY3JlZGVudGlhbHMuIEluY29ycmVjdCBwYXNzd29yZC4nLFxuICAgICAgICAgICAgfSksXG4gICAgICAgICAgKTtcbiAgICAgICAgfVxuXG4gICAgICAgIGlmICh1c2VyLnN0YXR1cyAhPT0gJ0FDVElWRScpIHtcbiAgICAgICAgICB0aHJvdyBuZXcgRXJyb3IoXG4gICAgICAgICAgICBKU09OLnN0cmluZ2lmeSh7XG4gICAgICAgICAgICAgIGNvZGU6IDQwMyxcbiAgICAgICAgICAgICAgbWVzc2FnZTogJ0FjY291bnQgbm90IGFjdGl2YXRlZC4gUGxlYXNlIHZlcmlmeSB5b3VyIGVtYWlsLicsXG4gICAgICAgICAgICB9KSxcbiAgICAgICAgICApO1xuICAgICAgICB9XG5cbiAgICAgICAgLy8gVXBkYXRlIGBsYXN0U2lnbkluQXRgIGZpZWxkXG4gICAgICAgIGF3YWl0IHByaXNtYS51c2VyLnVwZGF0ZSh7XG4gICAgICAgICAgd2hlcmU6IHsgaWQ6IHVzZXIuaWQgfSxcbiAgICAgICAgICBkYXRhOiB7IGxhc3RTaWduSW5BdDogbmV3IERhdGUoKSB9LFxuICAgICAgICB9KTtcblxuICAgICAgICByZXR1cm4ge1xuICAgICAgICAgIGlkOiB1c2VyLmlkLFxuICAgICAgICAgIHN0YXR1czogdXNlci5zdGF0dXMsXG4gICAgICAgICAgZW1haWw6IHVzZXIuZW1haWwsXG4gICAgICAgICAgbmFtZTogdXNlci5uYW1lIHx8ICdBbm9ueW1vdXMnLFxuICAgICAgICAgIHJvbGVJZDogdXNlci5yb2xlSWQsXG4gICAgICAgICAgYXZhdGFyOiB1c2VyLmF2YXRhcixcbiAgICAgICAgfTtcbiAgICAgIH0sXG4gICAgfSksXG4gICAgR29vZ2xlUHJvdmlkZXIoe1xuICAgICAgY2xpZW50SWQ6IHByb2Nlc3MuZW52LkdPT0dMRV9DTElFTlRfSUQhLFxuICAgICAgY2xpZW50U2VjcmV0OiBwcm9jZXNzLmVudi5HT09HTEVfQ0xJRU5UX1NFQ1JFVCEsXG4gICAgICBhbGxvd0Rhbmdlcm91c0VtYWlsQWNjb3VudExpbmtpbmc6IHRydWUsXG4gICAgICBhc3luYyBwcm9maWxlKHByb2ZpbGUpIHtcbiAgICAgICAgY29uc3QgZXhpc3RpbmdVc2VyID0gYXdhaXQgcHJpc21hLnVzZXIuZmluZFVuaXF1ZSh7XG4gICAgICAgICAgd2hlcmU6IHsgZW1haWw6IHByb2ZpbGUuZW1haWwgfSxcbiAgICAgICAgICBpbmNsdWRlOiB7XG4gICAgICAgICAgICByb2xlOiB7XG4gICAgICAgICAgICAgIHNlbGVjdDoge1xuICAgICAgICAgICAgICAgIGlkOiB0cnVlLFxuICAgICAgICAgICAgICAgIG5hbWU6IHRydWUsXG4gICAgICAgICAgICAgIH0sXG4gICAgICAgICAgICB9LFxuICAgICAgICAgIH0sXG4gICAgICAgIH0pO1xuXG4gICAgICAgIGlmIChleGlzdGluZ1VzZXIpIHtcbiAgICAgICAgICAvLyBVcGRhdGUgYGxhc3RTaWduSW5BdGAgZmllbGQgZm9yIGV4aXN0aW5nIHVzZXJzXG4gICAgICAgICAgYXdhaXQgcHJpc21hLnVzZXIudXBkYXRlKHtcbiAgICAgICAgICAgIHdoZXJlOiB7IGlkOiBleGlzdGluZ1VzZXIuaWQgfSxcbiAgICAgICAgICAgIGRhdGE6IHtcbiAgICAgICAgICAgICAgbmFtZTogcHJvZmlsZS5uYW1lLFxuICAgICAgICAgICAgICBhdmF0YXI6IHByb2ZpbGUucGljdHVyZSB8fCBudWxsLFxuICAgICAgICAgICAgICBsYXN0U2lnbkluQXQ6IG5ldyBEYXRlKCksXG4gICAgICAgICAgICB9LFxuICAgICAgICAgIH0pO1xuXG4gICAgICAgICAgcmV0dXJuIHtcbiAgICAgICAgICAgIGlkOiBleGlzdGluZ1VzZXIuaWQsXG4gICAgICAgICAgICBlbWFpbDogZXhpc3RpbmdVc2VyLmVtYWlsLFxuICAgICAgICAgICAgbmFtZTogZXhpc3RpbmdVc2VyLm5hbWUgfHwgJ0Fub255bW91cycsXG4gICAgICAgICAgICBzdGF0dXM6IGV4aXN0aW5nVXNlci5zdGF0dXMsXG4gICAgICAgICAgICByb2xlSWQ6IGV4aXN0aW5nVXNlci5yb2xlSWQsXG4gICAgICAgICAgICByb2xlTmFtZTogZXhpc3RpbmdVc2VyLnJvbGUubmFtZSxcbiAgICAgICAgICAgIGF2YXRhcjogZXhpc3RpbmdVc2VyLmF2YXRhcixcbiAgICAgICAgICB9O1xuICAgICAgICB9XG5cbiAgICAgICAgY29uc3QgZGVmYXVsdFJvbGUgPSBhd2FpdCBwcmlzbWEudXNlclJvbGUuZmluZEZpcnN0KHtcbiAgICAgICAgICB3aGVyZTogeyBpc0RlZmF1bHQ6IHRydWUgfSxcbiAgICAgICAgfSk7XG5cbiAgICAgICAgaWYgKCFkZWZhdWx0Um9sZSkge1xuICAgICAgICAgIHRocm93IG5ldyBFcnJvcihcbiAgICAgICAgICAgICdEZWZhdWx0IHJvbGUgbm90IGZvdW5kLiBVbmFibGUgdG8gY3JlYXRlIGEgbmV3IHVzZXIuJyxcbiAgICAgICAgICApO1xuICAgICAgICB9XG5cbiAgICAgICAgLy8gQ3JlYXRlIGEgbmV3IHVzZXIgYW5kIGFjY291bnRcbiAgICAgICAgY29uc3QgbmV3VXNlciA9IGF3YWl0IHByaXNtYS51c2VyLmNyZWF0ZSh7XG4gICAgICAgICAgZGF0YToge1xuICAgICAgICAgICAgZW1haWw6IHByb2ZpbGUuZW1haWwsXG4gICAgICAgICAgICBuYW1lOiBwcm9maWxlLm5hbWUsXG4gICAgICAgICAgICBwYXNzd29yZDogJycsIC8vIE5vIHBhc3N3b3JkIGZvciBPQXV0aCB1c2Vyc1xuICAgICAgICAgICAgYXZhdGFyOiBwcm9maWxlLnBpY3R1cmUgfHwgbnVsbCxcbiAgICAgICAgICAgIGVtYWlsVmVyaWZpZWRBdDogbmV3IERhdGUoKSxcbiAgICAgICAgICAgIHJvbGVJZDogZGVmYXVsdFJvbGUuaWQsXG4gICAgICAgICAgICBzdGF0dXM6ICdBQ1RJVkUnLFxuICAgICAgICAgIH0sXG4gICAgICAgIH0pO1xuXG4gICAgICAgIHJldHVybiB7XG4gICAgICAgICAgaWQ6IG5ld1VzZXIuaWQsXG4gICAgICAgICAgZW1haWw6IG5ld1VzZXIuZW1haWwsXG4gICAgICAgICAgbmFtZTogbmV3VXNlci5uYW1lIHx8ICdBbm9ueW1vdXMnLFxuICAgICAgICAgIHN0YXR1czogbmV3VXNlci5zdGF0dXMsXG4gICAgICAgICAgYXZhdGFyOiBuZXdVc2VyLmF2YXRhcixcbiAgICAgICAgICByb2xlSWQ6IG5ld1VzZXIucm9sZUlkLFxuICAgICAgICAgIHJvbGVOYW1lOiBkZWZhdWx0Um9sZS5uYW1lLFxuICAgICAgICB9O1xuICAgICAgfSxcbiAgICB9KSxcbiAgXSxcbiAgc2Vzc2lvbjoge1xuICAgIHN0cmF0ZWd5OiAnand0JyxcbiAgICBtYXhBZ2U6IDI0ICogNjAgKiA2MCxcbiAgfSxcbiAgY2FsbGJhY2tzOiB7XG4gICAgYXN5bmMgand0KHtcbiAgICAgIHRva2VuLFxuICAgICAgdXNlcixcbiAgICAgIHNlc3Npb24sXG4gICAgICB0cmlnZ2VyLFxuICAgIH06IHtcbiAgICAgIHRva2VuOiBKV1Q7XG4gICAgICB1c2VyOiBVc2VyO1xuICAgICAgc2Vzc2lvbj86IFNlc3Npb247XG4gICAgICB0cmlnZ2VyPzogJ3NpZ25JbicgfCAnc2lnblVwJyB8ICd1cGRhdGUnO1xuICAgIH0pIHtcbiAgICAgIGlmICh0cmlnZ2VyID09PSAndXBkYXRlJyAmJiBzZXNzaW9uPy51c2VyKSB7XG4gICAgICAgIHRva2VuID0gc2Vzc2lvbi51c2VyO1xuICAgICAgfSBlbHNlIHtcbiAgICAgICAgaWYgKHVzZXIgJiYgdXNlci5yb2xlSWQpIHtcbiAgICAgICAgICBjb25zdCByb2xlID0gYXdhaXQgcHJpc21hLnVzZXJSb2xlLmZpbmRVbmlxdWUoe1xuICAgICAgICAgICAgd2hlcmU6IHsgaWQ6IHVzZXIucm9sZUlkIH0sXG4gICAgICAgICAgfSk7XG5cbiAgICAgICAgICB0b2tlbi5pZCA9ICh1c2VyLmlkIHx8IHRva2VuLnN1YikgYXMgc3RyaW5nO1xuICAgICAgICAgIHRva2VuLmVtYWlsID0gdXNlci5lbWFpbDtcbiAgICAgICAgICB0b2tlbi5uYW1lID0gdXNlci5uYW1lO1xuICAgICAgICAgIHRva2VuLmF2YXRhciA9IHVzZXIuYXZhdGFyO1xuICAgICAgICAgIHRva2VuLnN0YXR1cyA9IHVzZXIuc3RhdHVzO1xuICAgICAgICAgIHRva2VuLnJvbGVJZCA9IHVzZXIucm9sZUlkO1xuICAgICAgICAgIHRva2VuLnJvbGVOYW1lID0gcm9sZT8ubmFtZTtcbiAgICAgICAgfVxuICAgICAgfVxuXG4gICAgICByZXR1cm4gdG9rZW47XG4gICAgfSxcbiAgICBhc3luYyBzZXNzaW9uKHsgc2Vzc2lvbiwgdG9rZW4gfTogeyBzZXNzaW9uOiBTZXNzaW9uOyB0b2tlbjogSldUIH0pIHtcbiAgICAgIGlmIChzZXNzaW9uLnVzZXIpIHtcbiAgICAgICAgc2Vzc2lvbi51c2VyLmlkID0gdG9rZW4uaWQ7XG4gICAgICAgIHNlc3Npb24udXNlci5lbWFpbCA9IHRva2VuLmVtYWlsO1xuICAgICAgICBzZXNzaW9uLnVzZXIubmFtZSA9IHRva2VuLm5hbWU7XG4gICAgICAgIHNlc3Npb24udXNlci5hdmF0YXIgPSB0b2tlbi5hdmF0YXI7XG4gICAgICAgIHNlc3Npb24udXNlci5zdGF0dXMgPSB0b2tlbi5zdGF0dXM7XG4gICAgICAgIHNlc3Npb24udXNlci5yb2xlSWQgPSB0b2tlbi5yb2xlSWQ7XG4gICAgICAgIHNlc3Npb24udXNlci5yb2xlTmFtZSA9IHRva2VuLnJvbGVOYW1lO1xuICAgICAgfVxuICAgICAgcmV0dXJuIHNlc3Npb247XG4gICAgfSxcbiAgfSxcbiAgcGFnZXM6IHtcbiAgICBzaWduSW46ICcvc2lnbmluJyxcbiAgfSxcbn07XG5cbmV4cG9ydCBkZWZhdWx0IGF1dGhPcHRpb25zO1xuIl0sIm5hbWVzIjpbIlByaXNtYUFkYXB0ZXIiLCJiY3J5cHQiLCJDcmVkZW50aWFsc1Byb3ZpZGVyIiwiR29vZ2xlUHJvdmlkZXIiLCJwcmlzbWEiLCJhdXRoT3B0aW9ucyIsImFkYXB0ZXIiLCJwcm92aWRlcnMiLCJuYW1lIiwiY3JlZGVudGlhbHMiLCJlbWFpbCIsImxhYmVsIiwidHlwZSIsInBhc3N3b3JkIiwicmVtZW1iZXJNZSIsImF1dGhvcml6ZSIsIkVycm9yIiwiSlNPTiIsInN0cmluZ2lmeSIsImNvZGUiLCJtZXNzYWdlIiwidXNlciIsImZpbmRVbmlxdWUiLCJ3aGVyZSIsImlzUGFzc3dvcmRWYWxpZCIsImNvbXBhcmUiLCJzdGF0dXMiLCJ1cGRhdGUiLCJpZCIsImRhdGEiLCJsYXN0U2lnbkluQXQiLCJEYXRlIiwicm9sZUlkIiwiYXZhdGFyIiwiY2xpZW50SWQiLCJwcm9jZXNzIiwiZW52IiwiR09PR0xFX0NMSUVOVF9JRCIsImNsaWVudFNlY3JldCIsIkdPT0dMRV9DTElFTlRfU0VDUkVUIiwiYWxsb3dEYW5nZXJvdXNFbWFpbEFjY291bnRMaW5raW5nIiwicHJvZmlsZSIsImV4aXN0aW5nVXNlciIsImluY2x1ZGUiLCJyb2xlIiwic2VsZWN0IiwicGljdHVyZSIsInJvbGVOYW1lIiwiZGVmYXVsdFJvbGUiLCJ1c2VyUm9sZSIsImZpbmRGaXJzdCIsImlzRGVmYXVsdCIsIm5ld1VzZXIiLCJjcmVhdGUiLCJlbWFpbFZlcmlmaWVkQXQiLCJzZXNzaW9uIiwic3RyYXRlZ3kiLCJtYXhBZ2UiLCJjYWxsYmFja3MiLCJqd3QiLCJ0b2tlbiIsInRyaWdnZXIiLCJzdWIiLCJwYWdlcyIsInNpZ25JbiJdLCJpZ25vcmVMaXN0IjpbXSwic291cmNlUm9vdCI6IiJ9\n//# sourceURL=webpack-internal:///(rsc)/./app/api/auth/[...nextauth]/auth-options.ts\n");

/***/ }),

/***/ "(rsc)/./app/api/auth/[...nextauth]/route.ts":
/*!*********************************************!*\
  !*** ./app/api/auth/[...nextauth]/route.ts ***!
  \*********************************************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

"use strict";
eval("__webpack_require__.r(__webpack_exports__);\n/* harmony export */ __webpack_require__.d(__webpack_exports__, {\n/* harmony export */   GET: () => (/* binding */ handler),\n/* harmony export */   POST: () => (/* binding */ handler)\n/* harmony export */ });\n/* harmony import */ var next_auth__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! next-auth */ \"(rsc)/./node_modules/next-auth/index.js\");\n/* harmony import */ var next_auth__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(next_auth__WEBPACK_IMPORTED_MODULE_0__);\n/* harmony import */ var _auth_options__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ./auth-options */ \"(rsc)/./app/api/auth/[...nextauth]/auth-options.ts\");\n\n\nconst handler = next_auth__WEBPACK_IMPORTED_MODULE_0___default()(_auth_options__WEBPACK_IMPORTED_MODULE_1__[\"default\"]);\n\n//# sourceURL=[module]\n//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiKHJzYykvLi9hcHAvYXBpL2F1dGgvWy4uLm5leHRhdXRoXS9yb3V0ZS50cyIsIm1hcHBpbmdzIjoiOzs7Ozs7OztBQUFpQztBQUNRO0FBRXpDLE1BQU1FLFVBQVVGLGdEQUFRQSxDQUFDQyxxREFBV0E7QUFFTyIsInNvdXJjZXMiOlsiL1VzZXJzL3RlaGpheXNvbi9Eb2N1bWVudHMvZm91bmRyeXgvc29yZW50b19jcm0vc29yZW50b19jcm1fZnJvbnRlbmQvYXBwL2FwaS9hdXRoL1suLi5uZXh0YXV0aF0vcm91dGUudHMiXSwic291cmNlc0NvbnRlbnQiOlsiaW1wb3J0IE5leHRBdXRoIGZyb20gJ25leHQtYXV0aCc7XG5pbXBvcnQgYXV0aE9wdGlvbnMgZnJvbSAnLi9hdXRoLW9wdGlvbnMnO1xuXG5jb25zdCBoYW5kbGVyID0gTmV4dEF1dGgoYXV0aE9wdGlvbnMpO1xuXG5leHBvcnQgeyBoYW5kbGVyIGFzIEdFVCwgaGFuZGxlciBhcyBQT1NUIH07XG4iXSwibmFtZXMiOlsiTmV4dEF1dGgiLCJhdXRoT3B0aW9ucyIsImhhbmRsZXIiLCJHRVQiLCJQT1NUIl0sImlnbm9yZUxpc3QiOltdLCJzb3VyY2VSb290IjoiIn0=\n//# sourceURL=webpack-internal:///(rsc)/./app/api/auth/[...nextauth]/route.ts\n");

/***/ }),

/***/ "(rsc)/./lib/prisma.ts":
/*!***********************!*\
  !*** ./lib/prisma.ts ***!
  \***********************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

"use strict";
eval("__webpack_require__.r(__webpack_exports__);\n/* harmony export */ __webpack_require__.d(__webpack_exports__, {\n/* harmony export */   \"default\": () => (__WEBPACK_DEFAULT_EXPORT__),\n/* harmony export */   prisma: () => (/* binding */ prisma)\n/* harmony export */ });\n/* harmony import */ var _prisma_client__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @prisma/client */ \"@prisma/client\");\n/* harmony import */ var _prisma_client__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_prisma_client__WEBPACK_IMPORTED_MODULE_0__);\n\nconst globalForPrisma = global;\nconst prisma = globalForPrisma.prisma || new _prisma_client__WEBPACK_IMPORTED_MODULE_0__.PrismaClient({\n    log:  true ? [\n        'query',\n        'info',\n        'warn',\n        'error'\n    ] : 0\n});\nif (true) {\n    globalForPrisma.prisma = prisma;\n}\n/* harmony default export */ const __WEBPACK_DEFAULT_EXPORT__ = (prisma);\n//# sourceURL=[module]\n//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiKHJzYykvLi9saWIvcHJpc21hLnRzIiwibWFwcGluZ3MiOiI7Ozs7Ozs7QUFBOEM7QUFFOUMsTUFBTUMsa0JBQWtCQztBQUVqQixNQUFNQyxTQUNYRixnQkFBZ0JFLE1BQU0sSUFDdEIsSUFBSUgsd0RBQVlBLENBQUM7SUFDZkksS0FDRUMsS0FBc0MsR0FDbEM7UUFBQztRQUFTO1FBQVE7UUFBUTtLQUFRLEdBQ2xDLENBQUU7QUFDVixHQUFHO0FBRUwsSUFBSUEsSUFBcUMsRUFBRTtJQUN6Q0osZ0JBQWdCRSxNQUFNLEdBQUdBO0FBQzNCO0FBRUEsaUVBQWVBLE1BQU1BLEVBQUMiLCJzb3VyY2VzIjpbIi9Vc2Vycy90ZWhqYXlzb24vRG9jdW1lbnRzL2ZvdW5kcnl4L3NvcmVudG9fY3JtL3NvcmVudG9fY3JtX2Zyb250ZW5kL2xpYi9wcmlzbWEudHMiXSwic291cmNlc0NvbnRlbnQiOlsiaW1wb3J0IHsgUHJpc21hQ2xpZW50IH0gZnJvbSAnQHByaXNtYS9jbGllbnQnO1xuXG5jb25zdCBnbG9iYWxGb3JQcmlzbWEgPSBnbG9iYWwgYXMgdW5rbm93biBhcyB7IHByaXNtYTogUHJpc21hQ2xpZW50IH07XG5cbmV4cG9ydCBjb25zdCBwcmlzbWEgPVxuICBnbG9iYWxGb3JQcmlzbWEucHJpc21hIHx8XG4gIG5ldyBQcmlzbWFDbGllbnQoe1xuICAgIGxvZzpcbiAgICAgIHByb2Nlc3MuZW52Lk5PREVfRU5WID09PSAnZGV2ZWxvcG1lbnQnXG4gICAgICAgID8gWydxdWVyeScsICdpbmZvJywgJ3dhcm4nLCAnZXJyb3InXVxuICAgICAgICA6IFtdLFxuICB9KTtcblxuaWYgKHByb2Nlc3MuZW52Lk5PREVfRU5WICE9PSAncHJvZHVjdGlvbicpIHtcbiAgZ2xvYmFsRm9yUHJpc21hLnByaXNtYSA9IHByaXNtYTtcbn1cblxuZXhwb3J0IGRlZmF1bHQgcHJpc21hO1xuIl0sIm5hbWVzIjpbIlByaXNtYUNsaWVudCIsImdsb2JhbEZvclByaXNtYSIsImdsb2JhbCIsInByaXNtYSIsImxvZyIsInByb2Nlc3MiXSwiaWdub3JlTGlzdCI6W10sInNvdXJjZVJvb3QiOiIifQ==\n//# sourceURL=webpack-internal:///(rsc)/./lib/prisma.ts\n");

/***/ }),

/***/ "(rsc)/./node_modules/next/dist/build/webpack/loaders/next-app-loader/index.js?name=app%2Fapi%2Fauth%2F%5B...nextauth%5D%2Froute&page=%2Fapi%2Fauth%2F%5B...nextauth%5D%2Froute&appPaths=&pagePath=private-next-app-dir%2Fapi%2Fauth%2F%5B...nextauth%5D%2Froute.ts&appDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend%2Fapp&pageExtensions=tsx&pageExtensions=ts&pageExtensions=jsx&pageExtensions=js&rootDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend&isDev=true&tsconfigPath=tsconfig.json&basePath=&assetPrefix=&nextConfigOutput=standalone&preferredRegion=&middlewareConfig=e30%3D!":
/*!************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************!*\
  !*** ./node_modules/next/dist/build/webpack/loaders/next-app-loader/index.js?name=app%2Fapi%2Fauth%2F%5B...nextauth%5D%2Froute&page=%2Fapi%2Fauth%2F%5B...nextauth%5D%2Froute&appPaths=&pagePath=private-next-app-dir%2Fapi%2Fauth%2F%5B...nextauth%5D%2Froute.ts&appDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend%2Fapp&pageExtensions=tsx&pageExtensions=ts&pageExtensions=jsx&pageExtensions=js&rootDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend&isDev=true&tsconfigPath=tsconfig.json&basePath=&assetPrefix=&nextConfigOutput=standalone&preferredRegion=&middlewareConfig=e30%3D! ***!
  \************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

"use strict";
eval("__webpack_require__.r(__webpack_exports__);\n/* harmony export */ __webpack_require__.d(__webpack_exports__, {\n/* harmony export */   patchFetch: () => (/* binding */ patchFetch),\n/* harmony export */   routeModule: () => (/* binding */ routeModule),\n/* harmony export */   serverHooks: () => (/* binding */ serverHooks),\n/* harmony export */   workAsyncStorage: () => (/* binding */ workAsyncStorage),\n/* harmony export */   workUnitAsyncStorage: () => (/* binding */ workUnitAsyncStorage)\n/* harmony export */ });\n/* harmony import */ var next_dist_server_route_modules_app_route_module_compiled__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! next/dist/server/route-modules/app-route/module.compiled */ \"(rsc)/./node_modules/next/dist/server/route-modules/app-route/module.compiled.js\");\n/* harmony import */ var next_dist_server_route_modules_app_route_module_compiled__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(next_dist_server_route_modules_app_route_module_compiled__WEBPACK_IMPORTED_MODULE_0__);\n/* harmony import */ var next_dist_server_route_kind__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! next/dist/server/route-kind */ \"(rsc)/./node_modules/next/dist/server/route-kind.js\");\n/* harmony import */ var next_dist_server_lib_patch_fetch__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! next/dist/server/lib/patch-fetch */ \"(rsc)/./node_modules/next/dist/server/lib/patch-fetch.js\");\n/* harmony import */ var next_dist_server_lib_patch_fetch__WEBPACK_IMPORTED_MODULE_2___default = /*#__PURE__*/__webpack_require__.n(next_dist_server_lib_patch_fetch__WEBPACK_IMPORTED_MODULE_2__);\n/* harmony import */ var _Users_tehjayson_Documents_foundryx_sorento_crm_sorento_crm_frontend_app_api_auth_nextauth_route_ts__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! ./app/api/auth/[...nextauth]/route.ts */ \"(rsc)/./app/api/auth/[...nextauth]/route.ts\");\n\n\n\n\n// We inject the nextConfigOutput here so that we can use them in the route\n// module.\nconst nextConfigOutput = \"standalone\"\nconst routeModule = new next_dist_server_route_modules_app_route_module_compiled__WEBPACK_IMPORTED_MODULE_0__.AppRouteRouteModule({\n    definition: {\n        kind: next_dist_server_route_kind__WEBPACK_IMPORTED_MODULE_1__.RouteKind.APP_ROUTE,\n        page: \"/api/auth/[...nextauth]/route\",\n        pathname: \"/api/auth/[...nextauth]\",\n        filename: \"route\",\n        bundlePath: \"app/api/auth/[...nextauth]/route\"\n    },\n    resolvedPagePath: \"/Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_frontend/app/api/auth/[...nextauth]/route.ts\",\n    nextConfigOutput,\n    userland: _Users_tehjayson_Documents_foundryx_sorento_crm_sorento_crm_frontend_app_api_auth_nextauth_route_ts__WEBPACK_IMPORTED_MODULE_3__\n});\n// Pull out the exports that we need to expose from the module. This should\n// be eliminated when we've moved the other routes to the new format. These\n// are used to hook into the route.\nconst { workAsyncStorage, workUnitAsyncStorage, serverHooks } = routeModule;\nfunction patchFetch() {\n    return (0,next_dist_server_lib_patch_fetch__WEBPACK_IMPORTED_MODULE_2__.patchFetch)({\n        workAsyncStorage,\n        workUnitAsyncStorage\n    });\n}\n\n\n//# sourceMappingURL=app-route.js.map//# sourceURL=[module]\n//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiKHJzYykvLi9ub2RlX21vZHVsZXMvbmV4dC9kaXN0L2J1aWxkL3dlYnBhY2svbG9hZGVycy9uZXh0LWFwcC1sb2FkZXIvaW5kZXguanM/bmFtZT1hcHAlMkZhcGklMkZhdXRoJTJGJTVCLi4ubmV4dGF1dGglNUQlMkZyb3V0ZSZwYWdlPSUyRmFwaSUyRmF1dGglMkYlNUIuLi5uZXh0YXV0aCU1RCUyRnJvdXRlJmFwcFBhdGhzPSZwYWdlUGF0aD1wcml2YXRlLW5leHQtYXBwLWRpciUyRmFwaSUyRmF1dGglMkYlNUIuLi5uZXh0YXV0aCU1RCUyRnJvdXRlLnRzJmFwcERpcj0lMkZVc2VycyUyRnRlaGpheXNvbiUyRkRvY3VtZW50cyUyRmZvdW5kcnl4JTJGc29yZW50b19jcm0lMkZzb3JlbnRvX2NybV9mcm9udGVuZCUyRmFwcCZwYWdlRXh0ZW5zaW9ucz10c3gmcGFnZUV4dGVuc2lvbnM9dHMmcGFnZUV4dGVuc2lvbnM9anN4JnBhZ2VFeHRlbnNpb25zPWpzJnJvb3REaXI9JTJGVXNlcnMlMkZ0ZWhqYXlzb24lMkZEb2N1bWVudHMlMkZmb3VuZHJ5eCUyRnNvcmVudG9fY3JtJTJGc29yZW50b19jcm1fZnJvbnRlbmQmaXNEZXY9dHJ1ZSZ0c2NvbmZpZ1BhdGg9dHNjb25maWcuanNvbiZiYXNlUGF0aD0mYXNzZXRQcmVmaXg9Jm5leHRDb25maWdPdXRwdXQ9c3RhbmRhbG9uZSZwcmVmZXJyZWRSZWdpb249Jm1pZGRsZXdhcmVDb25maWc9ZTMwJTNEISIsIm1hcHBpbmdzIjoiOzs7Ozs7Ozs7Ozs7OztBQUErRjtBQUN2QztBQUNxQjtBQUN3RDtBQUNySTtBQUNBO0FBQ0E7QUFDQSx3QkFBd0IseUdBQW1CO0FBQzNDO0FBQ0EsY0FBYyxrRUFBUztBQUN2QjtBQUNBO0FBQ0E7QUFDQTtBQUNBLEtBQUs7QUFDTDtBQUNBO0FBQ0EsWUFBWTtBQUNaLENBQUM7QUFDRDtBQUNBO0FBQ0E7QUFDQSxRQUFRLHNEQUFzRDtBQUM5RDtBQUNBLFdBQVcsNEVBQVc7QUFDdEI7QUFDQTtBQUNBLEtBQUs7QUFDTDtBQUMwRjs7QUFFMUYiLCJzb3VyY2VzIjpbIiJdLCJzb3VyY2VzQ29udGVudCI6WyJpbXBvcnQgeyBBcHBSb3V0ZVJvdXRlTW9kdWxlIH0gZnJvbSBcIm5leHQvZGlzdC9zZXJ2ZXIvcm91dGUtbW9kdWxlcy9hcHAtcm91dGUvbW9kdWxlLmNvbXBpbGVkXCI7XG5pbXBvcnQgeyBSb3V0ZUtpbmQgfSBmcm9tIFwibmV4dC9kaXN0L3NlcnZlci9yb3V0ZS1raW5kXCI7XG5pbXBvcnQgeyBwYXRjaEZldGNoIGFzIF9wYXRjaEZldGNoIH0gZnJvbSBcIm5leHQvZGlzdC9zZXJ2ZXIvbGliL3BhdGNoLWZldGNoXCI7XG5pbXBvcnQgKiBhcyB1c2VybGFuZCBmcm9tIFwiL1VzZXJzL3RlaGpheXNvbi9Eb2N1bWVudHMvZm91bmRyeXgvc29yZW50b19jcm0vc29yZW50b19jcm1fZnJvbnRlbmQvYXBwL2FwaS9hdXRoL1suLi5uZXh0YXV0aF0vcm91dGUudHNcIjtcbi8vIFdlIGluamVjdCB0aGUgbmV4dENvbmZpZ091dHB1dCBoZXJlIHNvIHRoYXQgd2UgY2FuIHVzZSB0aGVtIGluIHRoZSByb3V0ZVxuLy8gbW9kdWxlLlxuY29uc3QgbmV4dENvbmZpZ091dHB1dCA9IFwic3RhbmRhbG9uZVwiXG5jb25zdCByb3V0ZU1vZHVsZSA9IG5ldyBBcHBSb3V0ZVJvdXRlTW9kdWxlKHtcbiAgICBkZWZpbml0aW9uOiB7XG4gICAgICAgIGtpbmQ6IFJvdXRlS2luZC5BUFBfUk9VVEUsXG4gICAgICAgIHBhZ2U6IFwiL2FwaS9hdXRoL1suLi5uZXh0YXV0aF0vcm91dGVcIixcbiAgICAgICAgcGF0aG5hbWU6IFwiL2FwaS9hdXRoL1suLi5uZXh0YXV0aF1cIixcbiAgICAgICAgZmlsZW5hbWU6IFwicm91dGVcIixcbiAgICAgICAgYnVuZGxlUGF0aDogXCJhcHAvYXBpL2F1dGgvWy4uLm5leHRhdXRoXS9yb3V0ZVwiXG4gICAgfSxcbiAgICByZXNvbHZlZFBhZ2VQYXRoOiBcIi9Vc2Vycy90ZWhqYXlzb24vRG9jdW1lbnRzL2ZvdW5kcnl4L3NvcmVudG9fY3JtL3NvcmVudG9fY3JtX2Zyb250ZW5kL2FwcC9hcGkvYXV0aC9bLi4ubmV4dGF1dGhdL3JvdXRlLnRzXCIsXG4gICAgbmV4dENvbmZpZ091dHB1dCxcbiAgICB1c2VybGFuZFxufSk7XG4vLyBQdWxsIG91dCB0aGUgZXhwb3J0cyB0aGF0IHdlIG5lZWQgdG8gZXhwb3NlIGZyb20gdGhlIG1vZHVsZS4gVGhpcyBzaG91bGRcbi8vIGJlIGVsaW1pbmF0ZWQgd2hlbiB3ZSd2ZSBtb3ZlZCB0aGUgb3RoZXIgcm91dGVzIHRvIHRoZSBuZXcgZm9ybWF0LiBUaGVzZVxuLy8gYXJlIHVzZWQgdG8gaG9vayBpbnRvIHRoZSByb3V0ZS5cbmNvbnN0IHsgd29ya0FzeW5jU3RvcmFnZSwgd29ya1VuaXRBc3luY1N0b3JhZ2UsIHNlcnZlckhvb2tzIH0gPSByb3V0ZU1vZHVsZTtcbmZ1bmN0aW9uIHBhdGNoRmV0Y2goKSB7XG4gICAgcmV0dXJuIF9wYXRjaEZldGNoKHtcbiAgICAgICAgd29ya0FzeW5jU3RvcmFnZSxcbiAgICAgICAgd29ya1VuaXRBc3luY1N0b3JhZ2VcbiAgICB9KTtcbn1cbmV4cG9ydCB7IHJvdXRlTW9kdWxlLCB3b3JrQXN5bmNTdG9yYWdlLCB3b3JrVW5pdEFzeW5jU3RvcmFnZSwgc2VydmVySG9va3MsIHBhdGNoRmV0Y2gsICB9O1xuXG4vLyMgc291cmNlTWFwcGluZ1VSTD1hcHAtcm91dGUuanMubWFwIl0sIm5hbWVzIjpbXSwiaWdub3JlTGlzdCI6W10sInNvdXJjZVJvb3QiOiIifQ==\n//# sourceURL=webpack-internal:///(rsc)/./node_modules/next/dist/build/webpack/loaders/next-app-loader/index.js?name=app%2Fapi%2Fauth%2F%5B...nextauth%5D%2Froute&page=%2Fapi%2Fauth%2F%5B...nextauth%5D%2Froute&appPaths=&pagePath=private-next-app-dir%2Fapi%2Fauth%2F%5B...nextauth%5D%2Froute.ts&appDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend%2Fapp&pageExtensions=tsx&pageExtensions=ts&pageExtensions=jsx&pageExtensions=js&rootDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend&isDev=true&tsconfigPath=tsconfig.json&basePath=&assetPrefix=&nextConfigOutput=standalone&preferredRegion=&middlewareConfig=e30%3D!\n");

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

/***/ "@prisma/client":
/*!*********************************!*\
  !*** external "@prisma/client" ***!
  \*********************************/
/***/ ((module) => {

"use strict";
module.exports = require("@prisma/client");

/***/ }),

/***/ "assert":
/*!*************************!*\
  !*** external "assert" ***!
  \*************************/
/***/ ((module) => {

"use strict";
module.exports = require("assert");

/***/ }),

/***/ "bcrypt":
/*!*************************!*\
  !*** external "bcrypt" ***!
  \*************************/
/***/ ((module) => {

"use strict";
module.exports = require("bcrypt");

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

/***/ "querystring":
/*!******************************!*\
  !*** external "querystring" ***!
  \******************************/
/***/ ((module) => {

"use strict";
module.exports = require("querystring");

/***/ }),

/***/ "url":
/*!**********************!*\
  !*** external "url" ***!
  \**********************/
/***/ ((module) => {

"use strict";
module.exports = require("url");

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
var __webpack_exports__ = __webpack_require__.X(0, ["vendor-chunks/next","vendor-chunks/next-auth","vendor-chunks/@babel","vendor-chunks/jose","vendor-chunks/uuid","vendor-chunks/@panva","vendor-chunks/openid-client","vendor-chunks/oauth","vendor-chunks/yallist","vendor-chunks/preact-render-to-string","vendor-chunks/preact","vendor-chunks/oidc-token-hash","vendor-chunks/object-hash","vendor-chunks/lru-cache","vendor-chunks/cookie","vendor-chunks/@next-auth"], () => (__webpack_exec__("(rsc)/./node_modules/next/dist/build/webpack/loaders/next-app-loader/index.js?name=app%2Fapi%2Fauth%2F%5B...nextauth%5D%2Froute&page=%2Fapi%2Fauth%2F%5B...nextauth%5D%2Froute&appPaths=&pagePath=private-next-app-dir%2Fapi%2Fauth%2F%5B...nextauth%5D%2Froute.ts&appDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend%2Fapp&pageExtensions=tsx&pageExtensions=ts&pageExtensions=jsx&pageExtensions=js&rootDir=%2FUsers%2Ftehjayson%2FDocuments%2Ffoundryx%2Fsorento_crm%2Fsorento_crm_frontend&isDev=true&tsconfigPath=tsconfig.json&basePath=&assetPrefix=&nextConfigOutput=standalone&preferredRegion=&middlewareConfig=e30%3D!")));
module.exports = __webpack_exports__;

})();