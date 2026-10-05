// Estado de `/account/profile` (AUTH-02): carga el usuario actual con
// `GET /auth/me` y guarda nombre y datos de contacto con `PUT /profiles/me`.
// Solo consume services/auth.service.ts (nunca HTTP directo). Un 401 en
// cualquiera de las dos llamadas ya borró el token en lib/api-client.ts: el
// guard redirige a /login.
//
// Reducer puro + controlador sin React (probado con `node --test`) + hook.

import { useCallback, useEffect, useReducer, useState } from 'react';

import { ApiAbortError } from '@/lib/api-client';
import { AuthServiceError, getCurrentUser, updateProfile } from '@/services/auth.service';
import type { AuthUiError, CurrentUser, ProfileFormValues } from '@/types/auth';

export type ProfileLoadState =
  | { status: 'loading' }
  | { status: 'success'; user: CurrentUser }
  | { status: 'error'; error: AuthUiError };

export type ProfileSaveState =
  | { status: 'idle' }
  | { status: 'saving' }
  | { status: 'success' }
  | { status: 'error'; error: AuthUiError };

export interface ProfileState {
  load: ProfileLoadState;
  save: ProfileSaveState;
}

export type ProfileAction =
  | { type: 'load_started' }
  | { type: 'load_succeeded'; user: CurrentUser }
  | { type: 'load_failed'; error: AuthUiError }
  | { type: 'save_started' }
  | { type: 'save_succeeded'; profile: NonNullable<CurrentUser['profile']> }
  | { type: 'save_failed'; error: AuthUiError }
  | { type: 'save_reset' };

export const INITIAL_PROFILE_STATE: ProfileState = { load: { status: 'loading' }, save: { status: 'idle' } };

export function profileReducer(state: ProfileState, action: ProfileAction): ProfileState {
  switch (action.type) {
    case 'load_started':
      return { ...state, load: { status: 'loading' } };
    case 'load_succeeded':
      return { ...state, load: { status: 'success', user: action.user } };
    case 'load_failed':
      return { ...state, load: { status: 'error', error: action.error } };
    case 'save_started':
      return { ...state, save: { status: 'saving' } };
    case 'save_succeeded':
      // La respuesta de PUT /profiles/me es el perfil guardado: reemplaza al mostrado.
      return state.load.status === 'success'
        ? { load: { status: 'success', user: { ...state.load.user, profile: action.profile } }, save: { status: 'success' } }
        : { ...state, save: { status: 'success' } };
    case 'save_failed':
      return { ...state, save: { status: 'error', error: action.error } };
    case 'save_reset':
      return { ...state, save: { status: 'idle' } };
  }
}

export interface ProfileDependencies {
  getCurrentUser: typeof getCurrentUser;
  updateProfile: typeof updateProfile;
}

export interface ProfileController {
  activate(): void;
  dispose(): void;
  reload(): Promise<void>;
  save(values: ProfileFormValues): Promise<void>;
  resetSave(): void;
}

/** Error del servicio → AuthUiError; cualquier otro fallo, sin reenviar su texto. */
const FALLBACK_ERROR: AuthUiError = { kind: 'unexpected_response' };

export function createProfileController(
  dispatch: (action: ProfileAction) => void,
  dependencies: ProfileDependencies = { getCurrentUser, updateProfile }
): ProfileController {
  let active = false;
  let loadController: AbortController | null = null;
  let saveController: AbortController | null = null;

  function emit(action: ProfileAction): void {
    if (active) dispatch(action);
  }

  async function load(): Promise<void> {
    if (!active) return;
    loadController?.abort();
    const current = new AbortController();
    loadController = current;
    emit({ type: 'load_started' });
    try {
      const user = await dependencies.getCurrentUser({ signal: current.signal });
      if (loadController !== current) return;
      emit({ type: 'load_succeeded', user });
    } catch (error) {
      if (loadController !== current || error instanceof ApiAbortError) return;
      emit({ type: 'load_failed', error: error instanceof AuthServiceError ? error.uiError : FALLBACK_ERROR });
    } finally {
      if (loadController === current) loadController = null;
    }
  }

  return {
    activate() {
      if (active) return;
      active = true;
      void load();
    },

    dispose() {
      active = false;
      loadController?.abort();
      loadController = null;
      saveController?.abort();
      saveController = null;
    },

    reload: load,

    async save(values) {
      if (!active || saveController !== null) return;
      const current = new AbortController();
      saveController = current;
      emit({ type: 'save_started' });
      try {
        const profile = await dependencies.updateProfile(values, { signal: current.signal });
        if (saveController !== current) return;
        emit({ type: 'save_succeeded', profile });
      } catch (error) {
        if (saveController !== current || error instanceof ApiAbortError) return;
        emit({ type: 'save_failed', error: error instanceof AuthServiceError ? error.uiError : FALLBACK_ERROR });
      } finally {
        if (saveController === current) saveController = null;
      }
    },

    resetSave() {
      emit({ type: 'save_reset' });
    },
  };
}

export interface UseProfileResult extends ProfileState {
  reload: () => void;
  saveProfile: (values: ProfileFormValues) => void;
  resetSave: () => void;
}

export function useProfile(): UseProfileResult {
  const [state, dispatch] = useReducer(profileReducer, INITIAL_PROFILE_STATE);
  const [controller] = useState(() => createProfileController(dispatch));

  useEffect(() => {
    controller.activate();
    return () => controller.dispose();
  }, [controller]);

  const reload = useCallback(() => void controller.reload(), [controller]);
  const saveProfile = useCallback((values: ProfileFormValues) => void controller.save(values), [controller]);
  const resetSave = useCallback(() => controller.resetSave(), [controller]);

  return { ...state, reload, saveProfile, resetSave };
}
