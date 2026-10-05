// Estado de `/account/profile` (AUTH-02): carga el usuario con `GET /auth/me`
// y guarda nombre y contacto con `PUT /profiles/me` (services/api). Un 401 ya
// borró el token en lib/api-client.ts: el guard redirige a /login.

import { useCallback, useEffect, useRef, useState } from 'react';

import { describeApiError } from '@/lib/api-client';
import { describeAuthError, getCurrentUser, updateProfile } from '@/services/auth.service';
import type { AuthFormErrors, CurrentUser, ProfileFormValues } from '@/types/auth';

export type ProfileLoadState =
  | { status: 'loading' }
  | { status: 'success'; user: CurrentUser }
  | { status: 'error'; message: string };

export interface UseProfileResult {
  load: ProfileLoadState;
  isSaving: boolean;
  saveErrors: AuthFormErrors | null;
  reload: () => void;
  /** Devuelve `true` si la API guardó el perfil. */
  saveProfile: (values: ProfileFormValues) => Promise<boolean>;
}

export function useProfile(): UseProfileResult {
  const [load, setLoad] = useState<ProfileLoadState>({ status: 'loading' });
  const [isSaving, setIsSaving] = useState(false);
  const [saveErrors, setSaveErrors] = useState<AuthFormErrors | null>(null);
  // Descarta respuestas de cargas anteriores (recarga o desmontaje).
  const latestLoad = useRef(0);
  const saving = useRef(false);

  // Solo actualiza el estado cuando llega la respuesta (nunca de forma síncrona en el efecto).
  const fetchUser = useCallback(() => {
    const requestId = ++latestLoad.current;
    getCurrentUser()
      .then((user) => {
        if (latestLoad.current === requestId) setLoad({ status: 'success', user });
      })
      .catch((error: unknown) => {
        if (latestLoad.current === requestId) setLoad({ status: 'error', message: describeApiError(error) });
      });
  }, []);

  const reload = useCallback(() => {
    setLoad({ status: 'loading' });
    fetchUser();
  }, [fetchUser]);

  useEffect(() => {
    fetchUser();
    return () => {
      latestLoad.current += 1;
    };
  }, [fetchUser]);

  const saveProfile = useCallback(async (values: ProfileFormValues): Promise<boolean> => {
    if (saving.current) return false;
    saving.current = true;
    setIsSaving(true);
    setSaveErrors(null);
    try {
      const profile = await updateProfile(values);
      // La respuesta es el perfil guardado: reemplaza al mostrado.
      setLoad((current) =>
        current.status === 'success' ? { status: 'success', user: { ...current.user, profile } } : current
      );
      return true;
    } catch (error) {
      setSaveErrors(describeAuthError(error, 'account'));
      return false;
    } finally {
      saving.current = false;
      setIsSaving(false);
    }
  }, []);

  return { load, isSaving, saveErrors, reload, saveProfile };
}
