/**
 * Ideas service: the CRM-native Ideas pages' only door to the backend.
 *
 * PHASE 1: every function delegates to `ideasService.mock.ts` (in-memory, no network). Phase 2
 * replaces each body with `apiFetch` against the gateway below and deletes the mock; hooks and UI
 * do not change.
 *
 * EXPECTED CONTRACT (PLAN-ideation-in-crm section 10; bodies and responses are the ss embed API's
 * camelCase shapes, see `types/ideas.ts`; an ss 4xx arrives as the usual `{ detail }` error and is
 * thrown as `Error(message)` through `extractApiError`):
 *
 *   listIdeas         GET    /api/v1/ideation/ideas?filter=<status key>&query=      ideation.board.view
 *   getBoard          GET    /api/v1/ideation/ideas/board                           ideation.board.view
 *   getIdea           GET    /api/v1/ideation/ideas/{id}                            ideation.board.view
 *   getMergedChildren GET    /api/v1/ideation/ideas/{id}/merged                     ideation.board.view
 *   createIdea        POST   /api/v1/ideation/ideas  {problem, proposedSolution?, impact?, department?}
 *                            then POST .../ideas/{id}/attachments per file (multipart)  ideation.board.view
 *   updateIdea        PATCH  /api/v1/ideation/ideas/{id}  IdeaUpdateIn              ideation.ideas.manage
 *   voteIdea          POST   /api/v1/ideation/ideas/{id}/vote  {dir: 'up'}          ideation.board.view
 *   moveIdeaToStatus  POST   /api/v1/ideation/ideas/{id}/status  {toStatusId}       ideation.ideas.manage
 *   restoreIdea       POST   /api/v1/ideation/ideas/{id}/status  {status: 'new'}    ideation.ideas.manage
 *   archiveIdea       pending action `idea.archive` -> ss status {status: 'archived'}   ideation.ideas.manage
 *   deleteIdea        pending action `idea.delete`  -> ss DELETE /embed/ideas/{id}      ideation.ideas.manage
 *   reorderIdeas      PUT    /api/v1/ideation/ideas/reorder  {orderedIds}           ideation.ideas.manage
 *   mergeIdeas        POST   /api/v1/ideation/ideas/merge  {survivorId, ideaIds}    ideation.ideas.manage
 *   unmergeIdea       POST   /api/v1/ideation/ideas/{id}/unmerge                    ideation.ideas.manage
 *   promoteIdea       POST   /api/v1/ideation/ideas/promote  {title, ideaIds:[id]}  ideation.ideas.manage
 *                            ss answers 403 "This user has no Business Requirements access in the
 *                            Ideas workspace." when the CRM email has no BR-manage ss user.
 *   uploadAttachment  POST   /api/v1/ideation/ideas/{id}/attachments  (multipart)   ideation.ideas.manage
 *   listComments      GET    /api/v1/ideation/ideas/{id}/comments   (oldest first, one reply level)
 *   addComment        POST   /api/v1/ideation/ideas/{id}/comments  {body, parentId?}
 *   editComment       PATCH  /api/v1/ideation/ideas/{id}/comments/{cid}  {body}
 *   deleteComment     pending action `idea_comment.delete` -> DELETE .../comments/{cid}
 *
 * The Idea read carries one field ss does not return today: `businessRequirements` (the linked BRs,
 * read-only on the BR tab). The gateway adds it from ss's BR list filtered by the idea.
 */
import * as mock from '@/services/ideasService.mock';
import type {
  Idea,
  IdeaAttachment,
  IdeaBoard,
  IdeaComment,
  IdeaCreateInput,
  IdeaListParams,
  IdeaMergeInput,
  IdeaPromoteInput,
  IdeaUpdateInput,
} from '@/types/ideas';

export const IDEA_STATUS_FILTER_OPTIONS = mock.IDEA_STATUS_FILTER_OPTIONS;

export const listIdeas = (params: IdeaListParams): Promise<Idea[]> => mock.listIdeas(params);
export const getIdea = (id: string): Promise<Idea> => mock.getIdea(id);
export const getBoard = (): Promise<IdeaBoard> => mock.getBoard();
export const getMergedChildren = (id: string): Promise<Idea[]> => mock.getMergedChildren(id);
export const createIdea = (input: IdeaCreateInput): Promise<Idea> => mock.createIdea(input);
export const updateIdea = (id: string, input: IdeaUpdateInput): Promise<Idea> => mock.updateIdea(id, input);
export const voteIdea = (id: string): Promise<Idea> => mock.voteIdea(id);
export const moveIdeaToStatus = (id: string, toStatusId: string): Promise<Idea> =>
  mock.moveIdeaToStatus(id, toStatusId);
export const restoreIdea = (id: string): Promise<Idea> => mock.restoreIdea(id);
export const archiveIdea = (id: string): Promise<Idea> => mock.archiveIdea(id);
export const deleteIdea = (id: string): Promise<void> => mock.deleteIdea(id);
export const reorderIdeas = (orderedIds: string[]): Promise<void> => mock.reorderIdeas(orderedIds);
export const mergeIdeas = (input: IdeaMergeInput): Promise<Idea> => mock.mergeIdeas(input);
export const unmergeIdea = (id: string): Promise<Idea> => mock.unmergeIdea(id);
export const promoteIdea = (id: string, input: IdeaPromoteInput): Promise<Idea> => mock.promoteIdea(id, input);
export const uploadAttachment = (id: string, file: File): Promise<IdeaAttachment> =>
  mock.uploadAttachment(id, file);
export const listComments = (ideaId: string): Promise<IdeaComment[]> => mock.listComments(ideaId);
export const addComment = (ideaId: string, input: { body: string; parentId?: string | null }): Promise<IdeaComment> =>
  mock.addComment(ideaId, input);
export const editComment = (ideaId: string, commentId: string, body: string): Promise<IdeaComment> =>
  mock.editComment(ideaId, commentId, body);
export const deleteComment = (ideaId: string, commentId: string): Promise<void> =>
  mock.deleteComment(ideaId, commentId);
