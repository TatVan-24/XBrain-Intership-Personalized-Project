import styled from 'styled-components';

export const Page = styled.div`
  min-height: 65vh; display: grid; place-items: center; padding: 40px 20px;
`;
export const Card = styled.section`
  width: min(100%, 440px); padding: 32px; border: 1px solid #ddd; border-radius: 14px; background: white;
  h1 { margin-top: 0; }
  form { display: grid; gap: 18px; }
  label { display: grid; gap: 6px; font-weight: 700; }
  input { height: 46px; border: 1px solid #aaa; border-radius: 8px; padding: 0 12px; font-size: 16px; }
  .switch { margin-top: 18px; border: 0; background: none; color: #5262a8; cursor: pointer; }
`;
export const Error = styled.p`color: #a00020; margin: 0;`;
