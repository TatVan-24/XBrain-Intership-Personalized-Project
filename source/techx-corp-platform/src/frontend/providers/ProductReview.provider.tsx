// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { createContext, useContext, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import ApiGateway from '../gateways/Api.gateway';
import { ProductReview } from '../protos/demo';

interface IContext {
    // null = not loaded yet; [] = loaded with no reviews; array = loaded with reviews.
    productReviews: ProductReview[] | null;
    loading: boolean;
    error: Error | null;
    averageScore: string | null;
    totalReviews: number;
    ratingDistribution: number[];
    loadMore: () => void;
    createReview: (review: { description: string; score: number }) => Promise<void>;
    updateReview: (reviewId: number, review: { description: string; score: number }) => Promise<void>;
    deleteReview: (reviewId: number) => Promise<void>;
}

export const Context = createContext<IContext>({
    productReviews: null,
    loading: false,
    error: null,
    averageScore: null,
    totalReviews: 0, ratingDistribution: [0, 0, 0, 0, 0], loadMore: () => {},
    createReview: async () => {}, updateReview: async () => {}, deleteReview: async () => {},
});

interface IProps {
    children: React.ReactNode;
    productId: string;
}

//export const useProductReview = () => useContext(Context);
export const useProductReview = () => {
    const value = useContext(Context);
    return value;
};

const ProductReviewProvider = ({ children, productId }: IProps) => {
    const queryClient = useQueryClient();
    const [reviewLimit, setReviewLimit] = useState(5);
    const {
        data,
        isLoading,
        isFetching,
        isError,
        error,
        isSuccess,
    } = useQuery<{ items: ProductReview[]; total: number; distribution: number[] }>({
        queryKey: ['productReviews', productId, reviewLimit],
        queryFn: () => ApiGateway.getProductReviews(productId, reviewLimit),
        refetchOnWindowFocus: false,
        placeholderData: previousData => previousData,
    });

    // Use a sentinel: null while loading, [] if loaded but empty, array when loaded with data.
    const productReviews: ProductReview[] | null = isSuccess
        ? Array.isArray(data?.items)
            ? data.items
            : []
        : null;

    const loading = isLoading || isFetching;

    // Narrow react-query's `unknown` error to `Error | null`.
    const currentError: Error | null = isError
        ? error instanceof Error
            ? error
            : new Error('Unknown error')
        : null;

    const { data: averageScore = '' } = useQuery({
        queryKey: ['productReviewAvgScore', productId],
        queryFn: () => ApiGateway.getAverageProductReviewScore(productId),
    });

    const refresh = () => Promise.all([
        queryClient.invalidateQueries({ queryKey: ['productReviews', productId] }),
        queryClient.invalidateQueries({ queryKey: ['productReviewAvgScore', productId] }),
    ]).then(() => undefined);
    const createMutation = useMutation({ mutationFn: (review: { description: string; score: number }) => ApiGateway.createProductReview(productId, review), onSuccess: refresh });
    const updateMutation = useMutation({ mutationFn: ({ reviewId, review }: { reviewId: number; review: { description: string; score: number } }) => ApiGateway.updateProductReview(reviewId, review), onSuccess: refresh });
    const deleteMutation = useMutation({ mutationFn: (reviewId: number) => ApiGateway.deleteProductReview(reviewId), onSuccess: refresh });

    const value = useMemo(
        () => ({
            productReviews,
            loading,
            error: currentError,
            averageScore,
            totalReviews: data?.total || 0,
            ratingDistribution: data?.distribution || [0, 0, 0, 0, 0],
            loadMore: () => setReviewLimit(limit => limit + 5),
            createReview: async (review: { description: string; score: number }) => { await createMutation.mutateAsync(review); },
            updateReview: async (reviewId: number, review: { description: string; score: number }) => { await updateMutation.mutateAsync({ reviewId, review }); },
            deleteReview: async (reviewId: number) => { await deleteMutation.mutateAsync(reviewId); },
        }),
        [productReviews, loading, currentError, averageScore, data?.total, data?.distribution, createMutation, updateMutation, deleteMutation]
    );

    return <Context.Provider value={value}>{children}</Context.Provider>;
};

export default ProductReviewProvider;
