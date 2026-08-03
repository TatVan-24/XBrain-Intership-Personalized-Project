// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { NextPage } from 'next';
import Head from 'next/head';
import Layout from '../components/Layout';
import ProductList from '../components/ProductList';
import * as S from '../styles/Home.styled';
import { useQuery } from '@tanstack/react-query';
import ApiGateway from '../gateways/Api.gateway';
import Banner from '../components/Banner';
import { CypressFields } from '../utils/enums/CypressFields';
import { useCurrency } from '../providers/Currency.provider';
import { useState } from 'react';

const Home: NextPage = () => {
  const { selectedCurrency } = useCurrency();
  const [search, setSearch] = useState('');
  const { data: productList = [] } = useQuery({
    queryKey: ['products', selectedCurrency],
    queryFn: () => ApiGateway.listProducts(selectedCurrency),
  });

  return (
    <Layout>
      <Head>
        <title>Otel Demo - Home</title>
      </Head>
      <S.Home data-cy={CypressFields.HomePage}>
        <Banner />
        <S.Container>
          <S.Row>
            <S.Content>
              <S.HotProducts>
                <S.HotProductsTitle data-cy={CypressFields.HotProducts} id="hot-products">
                  Hot Products
                </S.HotProductsTitle>
                <S.Search
                  type="search"
                  value={search}
                  onChange={event => setSearch(event.target.value)}
                  placeholder="Search products by name, description or category"
                  aria-label="Search products"
                />
                <ProductList productList={productList.filter(product => {
                  const query = search.trim().toLowerCase();
                  return !query || [product.name, product.description, ...(product.categories || [])]
                    .some(value => value.toLowerCase().includes(query));
                })} />
              </S.HotProducts>
            </S.Content>
          </S.Row>
        </S.Container>
      </S.Home>
    </Layout>
  );
};

export default Home;
