import{e as c,j as t}from"./index-DwjriXk5.js";/**
 * @license lucide-react v0.468.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const r=c("CircleCheck",[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"m9 12 2 2 4-4",key:"dzmm74"}]]),o={date:"",employee_id:""};function m(a){return Object.fromEntries(Object.entries(a).filter(([,l])=>l))}function s({filters:a,setFilters:l,users:n=[]}){return t.jsxs("section",{className:"filterBar",children:[n.length?t.jsxs("select",{value:a.employee_id,onChange:e=>l({...a,employee_id:e.target.value}),children:[t.jsx("option",{value:"",children:"All employees"}),n.map(e=>t.jsxs("option",{value:e.employee_id,children:[e.employee_name," (",e.employee_id,")"]},e.user_id))]}):null,t.jsx("input",{type:"date",value:a.date,onChange:e=>l({...a,date:e.target.value})}),t.jsx("button",{className:"secondaryButton",onClick:()=>l(o),children:"Clear"})]})}export{r as C,s as F,m as c,o as e};
