// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import CartIcon from '../CartIcon';
import CurrencySwitcher from '../CurrencySwitcher';
import * as S from './Header.styled';
import { useAuth } from '../../providers/Auth.provider';

const Header = () => {
  const { user, loading, logout } = useAuth();
  return (
    <S.Header>
      <S.NavBar>
        <S.Container>
          <S.NavBarBrand href="/">
            <S.BrandImg />
          </S.NavBarBrand>
          <S.Controls>
            {!loading && (user ? (
              <S.Account>
                <span>Hello, {user.username}</span>
                <button type="button" onClick={logout}>Logout</button>
              </S.Account>
            ) : <S.AuthLink href="/auth">Login / Register</S.AuthLink>)}
            <CurrencySwitcher />
            <CartIcon />
          </S.Controls>
        </S.Container>
      </S.NavBar>
    </S.Header>
  );
};

export default Header;
