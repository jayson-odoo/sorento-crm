import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import StockDashboard from './components/StockDashboard';
import StockBalanceGrid from './components/StockBalanceGrid';

export default function StockPage() {
  return (
    <Tabs defaultValue="dashboard" className="w-full">
      <TabsList>
        <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
        <TabsTrigger value="balance">Stock Balance</TabsTrigger>
      </TabsList>
      <TabsContent value="dashboard">
        <StockDashboard />
      </TabsContent>
      <TabsContent value="balance">
        <StockBalanceGrid />
      </TabsContent>
    </Tabs>
  );
}
