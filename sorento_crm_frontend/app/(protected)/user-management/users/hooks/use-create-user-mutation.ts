import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createUser, type CreateUserInput } from '../services/userService';

/**
 * The Add user modal's save (S3 2.1): one call, no invitation branch. On
 * success invalidates the users list and, when the user was linked from a
 * contact, that contact's list row and detail read too.
 */
export const useCreateUserMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateUserInput) => createUser(input),
    onSuccess: (_user, variables) => {
      queryClient.invalidateQueries({ queryKey: ['user-users'] });
      queryClient.invalidateQueries({ queryKey: ['respond-contacts'] });
      if (variables.respond_contact_id) {
        queryClient.invalidateQueries({
          queryKey: ['respond-contact', variables.respond_contact_id],
        });
      }
    },
  });
};
