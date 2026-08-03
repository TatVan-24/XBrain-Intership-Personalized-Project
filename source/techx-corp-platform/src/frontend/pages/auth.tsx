import Head from 'next/head';
import { FormEvent, useState } from 'react';
import { useRouter } from 'next/router';
import Layout from '../components/Layout';
import Button from '../components/Button';
import { useAuth } from '../providers/Auth.provider';
import * as S from '../styles/Auth.styled';

export default function AuthPage() {
  const router = useRouter();
  const { login, register } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const credentials = { email, password, ...(mode === 'register' ? { username } : {}) };
      await (mode === 'login' ? login(credentials) : register(credentials));
      await router.push('/');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Request failed');
    } finally {
      setSubmitting(false);
    }
  };

  return <Layout>
    <Head><title>{mode === 'login' ? 'Login' : 'Register'} - XBrain</title></Head>
    <S.Page><S.Card>
      <h1>{mode === 'login' ? 'Login' : 'Create account'}</h1>
      <form onSubmit={submit}>
        {mode === 'register' && <label>Username<input required minLength={3} value={username} onChange={e => setUsername(e.target.value)} /></label>}
        <label>Email<input required type="email" value={email} onChange={e => setEmail(e.target.value)} /></label>
        <label>Password<input required type="password" minLength={mode === 'register' ? 10 : 1} value={password} onChange={e => setPassword(e.target.value)} /></label>
        {error && <S.Error role="alert">{error}</S.Error>}
        <Button disabled={submitting}>{submitting ? 'Please wait…' : mode === 'login' ? 'Login' : 'Register'}</Button>
      </form>
      <button className="switch" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}>
        {mode === 'login' ? 'New here? Register' : 'Already registered? Login'}
      </button>
    </S.Card></S.Page>
  </Layout>;
}
